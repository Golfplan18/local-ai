"""Persistent, Dialogue-bound management interview for governed construction.

Phase 2.2 creates one exact Programming Process Run and advances it only to the
nonmutating ``intent-interview`` node.  Interview observations live in the
Run's append-only event stream; the Dialogue stores only an immutable binding
pointer.  No canonical plan, execution authority, mutation, registration, or
activation is created here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import process_contracts as _contracts
    from conversation_memory import (
        ConversationProcessBindingError,
        bind_governing_process,
        ensure_conversation_envelope,
        load_conversation_json,
        load_governing_process_binding,
    )
    from governed_process_runtime import (
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from framework_invocability import (
        is_process_definition_framework,
        is_user_pickable_framework,
    )
    from process_entry_routing import load_programming_definition
except ImportError:  # pragma: no cover - package-qualified imports
    from orchestrator import process_contracts as _contracts
    from orchestrator.conversation_memory import (
        ConversationProcessBindingError,
        bind_governing_process,
        ensure_conversation_envelope,
        load_conversation_json,
        load_governing_process_binding,
    )
    from orchestrator.governed_process_runtime import (
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from orchestrator.framework_invocability import (
        is_process_definition_framework,
        is_user_pickable_framework,
    )
    from orchestrator.process_entry_routing import load_programming_definition


INTERVIEW_SCHEMA_VERSION = "ora.management-interview/1.0"
BINDING_SCHEMA_VERSION = "ora.dialogue-process-binding/1.0"
INTERVIEW_NODE_ID = "intent-interview"
ENTRYPOINT = "prg_run"
OBSERVATION_EVENT_TYPE = "dialogue_observation_recorded"

INTERVIEW_DIMENSIONS = (
    "intended_result",
    "affected_parties",
    "inputs_outputs",
    "reuse",
    "initiation",
    "authority",
    "exceptions",
    "permissions",
    "evidence",
    "stopping",
)

_QUESTIONS: dict[str, dict[str, str]] = {
    "intended_result": {
        "prompt": "What exact result should exist when this work is successful?",
        "evidence": "The submitted objective does not identify a concrete result.",
        "consequence": "The result boundary controls what the capability may produce and what completion means.",
    },
    "affected_parties": {
        "prompt": "Who will use the result, and who else could be affected by it?",
        "evidence": "The intended result is known, but its users and affected parties are not.",
        "consequence": "This determines whose needs, risks, and authority the later plan must represent.",
    },
    "inputs_outputs": {
        "prompt": "What should it read or receive, and exactly what should it produce or change?",
        "evidence": "The request does not yet bind both its inputs and outputs.",
        "consequence": "Those boundaries determine artifact scope and prevent unrelated data or systems from entering the work.",
    },
    "reuse": {
        "prompt": "Is this a one-time result, a repeatable procedure, or a reusable capability for later Runs?",
        "evidence": "The required reuse boundary cannot be inferred from the current request.",
        "consequence": "Reuse changes whether formalization, versioning, registration, and later invocation are required.",
    },
    "initiation": {
        "prompt": "What should start the work: a person, a schedule, or a specific event?",
        "evidence": "No exact initiation condition has been established.",
        "consequence": "The start condition controls whether the capability remains manual or may later be activated.",
    },
    "authority": {
        "prompt": "Which decisions may Ora make on its own, and which decisions must return to you?",
        "evidence": "The request does not yet define delegated versus reserved decisions.",
        "consequence": "The answer bounds judgment and prevents silent expansion of authority.",
    },
    "exceptions": {
        "prompt": "Which exceptional cases should be handled automatically, and which should stop and return to you?",
        "evidence": "No exception policy has been supplied.",
        "consequence": "The exception boundary determines correction, escalation, and true blockage behavior.",
    },
    "permissions": {
        "prompt": "Which data, files, systems, or external services may it inspect or change?",
        "evidence": "The required read, write, and external-effect permissions are unresolved.",
        "consequence": "These permissions become the later Run's enforceable artifact and effect scope.",
    },
    "evidence": {
        "prompt": "What proof should demonstrate that the result is correct and safe to accept?",
        "evidence": "No acceptance evidence has been specified.",
        "consequence": "The proof standard controls independent review and prevents unsupported completion.",
    },
    "stopping": {
        "prompt": "When must the work stop, pause, or ask for your decision?",
        "evidence": "The stopping and return conditions are not yet explicit.",
        "consequence": "Those conditions prevent blind continuation when evidence, permission, or safe progress runs out.",
    },
}

_REUSE_SIGNAL = re.compile(
    r"\b(?:automat(?:e|ed|es|ic|ically|ion)|ongoing|recurring|repeatable|"
    r"reusable|standing|workflow|process|capability)\b",
    flags=re.IGNORECASE,
)
_INITIATION_SIGNAL = re.compile(
    r"\b(?:hourly|daily|nightly|weekly|monthly|quarterly|annually|yearly)\b|"
    r"\b(?:every|each)\s+(?:(?:other|\d+)\s+)?(?:minute|hour|day|night|weekday|"
    r"week|month|quarter|year|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday)s?\b|"
    r"\b(?:whenever|every\s+time|each\s+time)\b|"
    r"\bwhen\b.{0,120}\b(?:arrives?|changes?|completes?|fails?|is\s+(?:added|"
    r"created|modified|received|updated))\b",
    flags=re.IGNORECASE,
)
_AFFECTED_PARTIES_SIGNAL = re.compile(
    r"\b(?:for|used\s+by|serves?)\s+(?:the\s+)?(?:"
    r"(?:finance|operations?|sales|support|legal|compliance|engineering|product|"
    r"management|executive|accounting|audit)\s+(?:team|department|staff|users?)|"
    r"customers?|clients?|employees?|auditors?|managers?|stakeholders?|the\s+principal|me)\b",
    flags=re.IGNORECASE,
)
_INPUT_SIGNAL = re.compile(
    r"\b(?:from|using|based\s+on|reads?|receives?|takes?\s+as\s+input)\b.{1,120}",
    flags=re.IGNORECASE,
)
_OUTPUT_SIGNAL = re.compile(
    r"\b(?:creates?|delivers?|emails?|generates?|outputs?|produces?|sends?|"
    r"updates?|writes?)\b",
    flags=re.IGNORECASE,
)
_AUTHORITY_SIGNAL = re.compile(
    r"\b(?:ora|the\s+system|it)\s+(?:may|can|cannot|must|must\s+not)\b|"
    r"\b(?:without|before)\s+(?:asking|approval)\b|"
    r"\b(?:requires?|needs?)\s+(?:my|principal|human)\s+approval\b|"
    r"\bapproval\s+(?:is|must\s+be)\s+required\b",
    flags=re.IGNORECASE,
)
_EXCEPTION_SIGNAL = re.compile(
    r"\b(?:except|unless)\b|"
    r"\bif\b.{0,100}\b(?:error|exception|fails?|invalid|missing|unavailable)\b",
    flags=re.IGNORECASE,
)
_PERMISSION_SIGNAL = re.compile(
    r"\b(?:may|can|permission\s+to|allowed\s+to)\s+"
    r"(?:access|change|delete|email|modify|read|send|write)\b|"
    r"\baccess\s+to\b",
    flags=re.IGNORECASE,
)
_EVIDENCE_SIGNAL = re.compile(
    r"\b(?:accept(?:ed)?\s+when|evidence|proof|verified|verification|verify)\b|"
    r"\b(?:all\s+|the\s+)?tests?\s+(?:must\s+|should\s+|will\s+)?pass(?:es|ed)?\b|"
    r"\bpasses?\s+(?:all\s+|the\s+)?(?:checks?|tests?|verification)\b|"
    r"\b(?:passing\s+)?(?:test|check|review)\s+(?:output|results?|report)\b",
    flags=re.IGNORECASE,
)
_STOPPING_SIGNAL = re.compile(
    r"\b(?:ask\s+me|escalate|halt|pause|return\s+to\s+me|stop)\b",
    flags=re.IGNORECASE,
)
_NONANSWER_SIGNAL = re.compile(
    r"^(?:i\s+(?:(?:do\s+not|don't|cannot|can't)\s+"
    r"(?:know|answer|say|decide)(?:\s+(?:that|this|yet|who|what|when|where|how))?|"
    r"have\s+no\s+(?:idea|preference|information))|i'm\s+not\s+sure|"
    r"not\s+sure|not\s+applicable|unsure|unknown|no\s+(?:idea|comment)|"
    r"tbd(?:\s+later)?|to\s+be\s+determined|skip|pass|whatever|anything|"
    r"you\s+decide|can\s+you\s+decide|as\s+needed|n/?a|none\s+provided|"
    r"maybe|perhaps)[.!?]*$",
    flags=re.IGNORECASE,
)
_NONANSWER_PREFIX_SIGNAL = re.compile(
    r"^(?:i\s+(?:(?:do\s+not|don't|cannot|can't)\s+"
    r"(?:know|answer|say|decide|provide|specify)|"
    r"have\s+no\s+(?:idea|preference|information|answer|result))|"
    r"i'm\s+not\s+sure|"
    r"not\s+sure|unsure|unknown|maybe|perhaps)\b",
    flags=re.IGNORECASE,
)
_CONCRETE_INTENT_GENERIC_TOKENS = {
    "a", "an", "and", "as", "at", "automate", "automated", "automation",
    "be", "build", "built", "by", "capability", "construct", "create",
    "created", "develop", "do", "establish", "for", "from", "implement",
    "in", "it", "make", "made", "my", "new", "of", "on", "our",
    "process", "repeatable", "reusable", "set", "solution", "something",
    "system", "task", "that", "the", "thing", "this", "to", "tool", "up",
    "using", "with", "work", "workflow",
}
_REUSE_ANSWER_SIGNAL = re.compile(
    r"\b(?:one[ -]time|once|repeatable|reusable|recurring|ongoing|"
    r"each\s+run|every\s+run|later\s+runs?|future\s+runs?|not\s+(?:reused|repeatable))\b",
    flags=re.IGNORECASE,
)
_MANUAL_INITIATION_SIGNAL = re.compile(
    r"\b(?:manually|on\s+demand|when\s+(?:i|we|a\s+user|the\s+user)\s+"
    r"(?:ask|start|request|run)|started\s+by|triggered\s+by|"
    r"(?:a|the)\s+(?:person|user|principal)\s+(?:starts?|initiates?|runs?))\b",
    flags=re.IGNORECASE,
)
_PARTY_ANSWER_SIGNAL = re.compile(
    r"\b(?:team|department|staff|users?|customers?|clients?|employees?|"
    r"auditors?|managers?|stakeholders?|principal|operators?|reviewers?|"
    r"finance|operations?|sales|support|legal|compliance|engineering|product|"
    r"management|executive|accounting|audit|(?:for|affects?|used\s+by)\s+me|"
    r"only\s+me|me\s+and|i\s+(?:will\s+)?use|"
    r"we\s+(?:will\s+)?use)\b",
    flags=re.IGNORECASE,
)
_NO_EXCEPTION_SIGNAL = re.compile(
    r"\b(?:no\s+exceptions?|all\s+(?:errors?|failures?)|every\s+(?:error|failure))\b",
    flags=re.IGNORECASE,
)
_SERVICE_LOCK = threading.RLock()


class ManagementInterviewError(RuntimeError):
    """Base class for refused or invalid management-interview operations."""


class ManagementInterviewConflict(ManagementInterviewError):
    """The requested operation conflicts with the active governing Run."""


class ManagementInterviewIntegrityError(ManagementInterviewError):
    """Persisted Dialogue, Run, definition, or observation identity drifted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _is_nonanswer(text: str) -> bool:
    normalized = " ".join(str(text or "").split())
    if _NONANSWER_SIGNAL.fullmatch(normalized) is not None:
        return True
    return (
        _NONANSWER_PREFIX_SIGNAL.search(normalized) is not None
        and re.search(r"\b(?:but|however)\b", normalized, flags=re.IGNORECASE) is None
    )


def _concrete_intended_result(text: str) -> bool:
    """Require a named result, not merely a generic construction category."""

    normalized = " ".join(str(text or "").split())
    if _is_nonanswer(normalized):
        return False
    informative = [
        token for token in re.findall(r"[a-z0-9]+", normalized.casefold())
        if token not in _CONCRETE_INTENT_GENERIC_TOKENS
        and not re.fullmatch(
            r"(?:hourly|daily|nightly|weekly|monthly|quarterly|annually|yearly)",
            token,
        )
    ]
    # Two content-bearing terms are the minimum evidence for an exact result.
    # This rejects goals such as "Build a reusable automation" while accepting
    # concrete results such as "a reconciled cash-flow report" or "an API endpoint".
    return len(informative) >= 2


def _materially_resolves(dimension: str, text: str) -> bool:
    """Return whether text supplies the management fact a dimension requires."""

    normalized = " ".join(str(text or "").split())
    if not normalized or _is_nonanswer(normalized):
        return False
    if dimension == "intended_result":
        return _concrete_intended_result(normalized)
    if dimension == "affected_parties":
        return _PARTY_ANSWER_SIGNAL.search(normalized) is not None
    if dimension == "inputs_outputs":
        return (
            _INPUT_SIGNAL.search(normalized) is not None
            and _OUTPUT_SIGNAL.search(normalized) is not None
        )
    if dimension == "reuse":
        return _REUSE_ANSWER_SIGNAL.search(normalized) is not None
    if dimension == "initiation":
        return (
            _INITIATION_SIGNAL.search(normalized) is not None
            or _MANUAL_INITIATION_SIGNAL.search(normalized) is not None
        )
    if dimension == "authority":
        return _AUTHORITY_SIGNAL.search(normalized) is not None
    if dimension == "exceptions":
        return (
            _EXCEPTION_SIGNAL.search(normalized) is not None
            or _NO_EXCEPTION_SIGNAL.search(normalized) is not None
        )
    if dimension == "permissions":
        return _PERMISSION_SIGNAL.search(normalized) is not None
    if dimension == "evidence":
        return _EVIDENCE_SIGNAL.search(normalized) is not None
    if dimension == "stopping":
        return _STOPPING_SIGNAL.search(normalized) is not None
    return False


def _default_answer_idempotency_key(dialogue_ref: str, answer: str) -> str:
    return "answer:" + _digest_json({
        "dialogue_ref": dialogue_ref,
        "answer": answer,
    }).removeprefix("sha256:")


def _normalize_answer_idempotency_key(value: str) -> str:
    key = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", key):
        raise ManagementInterviewError("management answer idempotency key is invalid")
    return key


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _binding_digest(
    dialogue_ref: str,
    run_id: str,
    definition_ref: Mapping[str, Any],
) -> str:
    return _digest_json({
        "schema_version": BINDING_SCHEMA_VERSION,
        "dialogue_ref": dialogue_ref,
        "run_id": run_id,
        "definition_ref": dict(definition_ref),
    })


def _run_id(
    dialogue_ref: str,
    project_ref: str,
    objective: str,
    definition_ref: Mapping[str, Any],
) -> str:
    identity = _digest_json({
        "dialogue_ref": dialogue_ref,
        "project_ref": project_ref,
        "objective": objective,
        "definition_ref": dict(definition_ref),
    })
    return "run-management-" + identity.removeprefix("sha256:")[:24]


def _validate_route_contract(route: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(route, Mapping):
        raise ManagementInterviewError("construction route must be an object")
    contract = copy.deepcopy(dict(route))
    supplied_digest = str(contract.pop("contract_digest", ""))
    if supplied_digest != _digest_json(contract):
        raise ManagementInterviewIntegrityError(
            "construction route contract digest does not match its content"
        )
    if (
        contract.get("schema_version") != "ora.process-entry/1.0"
        or contract.get("intent") != "capability_construction"
        or contract.get("status") != "ready"
        or contract.get("next_action") != "begin_management_interview"
        or contract.get("project_confirmed") is not True
        or contract.get("creates_process_run") is not False
        or contract.get("authority_effects") != []
    ):
        raise ManagementInterviewError(
            "management interview requires a confirmed, authority-neutral construction route"
        )
    objective = str(contract.get("objective") or "").strip()
    project_ref = str(contract.get("project_ref") or "").strip()
    if not objective or not project_ref:
        raise ManagementInterviewError(
            "construction route must bind an objective and confirmed project"
        )
    contract["contract_digest"] = supplied_digest
    return contract


def _explicit_answers(text: str, *, source_prefix: str) -> dict[str, dict[str, str]]:
    """Extract only high-confidence, explicit management facts from prose."""

    normalized = " ".join(str(text or "").split())
    answers: dict[str, dict[str, str]] = {}
    initiation = _INITIATION_SIGNAL.search(normalized)
    if _REUSE_SIGNAL.search(normalized) or initiation is not None:
        answers["reuse"] = {
            "answer": "The request establishes a repeatable or reusable capability.",
            "source": f"{source_prefix}_reuse_signal",
        }
    if _AFFECTED_PARTIES_SIGNAL.search(normalized):
        answers["affected_parties"] = {
            "answer": normalized,
            "source": f"{source_prefix}_affected_parties",
        }
    if _INPUT_SIGNAL.search(normalized) and _OUTPUT_SIGNAL.search(normalized):
        answers["inputs_outputs"] = {
            "answer": normalized,
            "source": f"{source_prefix}_inputs_outputs",
        }
    if initiation is not None:
        answers["initiation"] = {
            "answer": initiation.group(0).strip(),
            "source": f"{source_prefix}_initiation_signal",
        }
    signals = (
        ("authority", _AUTHORITY_SIGNAL),
        ("exceptions", _EXCEPTION_SIGNAL),
        ("permissions", _PERMISSION_SIGNAL),
        ("evidence", _EVIDENCE_SIGNAL),
        ("stopping", _STOPPING_SIGNAL),
    )
    for dimension, pattern in signals:
        if pattern.search(normalized):
            answers[dimension] = {
                "answer": normalized,
                "source": f"{source_prefix}_{dimension}",
            }
    return {
        dimension: fact
        for dimension, fact in answers.items()
        if _materially_resolves(dimension, fact["answer"])
    }


def _initial_answers(route: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    objective = str(route["objective"]).strip()
    answers = _explicit_answers(objective, source_prefix="submitted")
    if _materially_resolves("intended_result", objective):
        answers = {
            "intended_result": {
                "answer": objective,
                "source": "submitted_objective",
            },
            **answers,
        }
    return answers


def _interview_contracts(
    *,
    run_id: str,
    principal_id: str,
    approved_at: str,
    entry_contract_digest: str,
) -> dict[str, Any]:
    plan_body = {
        "plan_id": f"interview-{run_id}",
        "version": "1.0",
        "objective": "Conduct only the persistent management interview for this Dialogue.",
        "approved_by": principal_id,
        "approved_at": approved_at,
        "approved_node_ids": ["entry-route", INTERVIEW_NODE_ID],
        "constraints": [
            "Ask only unresolved management questions.",
            "Remain nonmutating and bound to the exact Dialogue.",
            "Do not create or approve the Phase 2.3 canonical plan.",
            f"Bind exact Phase 2.1 entry contract {entry_contract_digest}.",
        ],
        "non_goals": [
            "Do not inspect or mutate target systems.",
            "Do not register, invoke, publish, or activate a capability.",
        ],
    }
    approved_plan = {
        **plan_body,
        "digest": _digest_json(plan_body),
    }
    return {
        "approved_plan": approved_plan,
        "authority": {
            "principal_id": principal_id,
            "grants": [{
                "grant_id": "grant-dialogue",
                "actions": ["elicit_programming_intent"],
                "resource_selectors": ["scope:dialogue", "scope:declared_inputs"],
                "effect_types": ["dialogue_only"],
                "conditions": ["exact_dialogue_binding", "no_target_mutation"],
            }],
            "reserved_actions": [
                "activate", "construct_definition", "execute", "expand_scope",
                "inspect_target", "invoke_process", "mutate", "publish",
                "register_definition",
            ],
        },
        "artifact_scope": {
            "read_selectors": ["scope:dialogue", "scope:declared_inputs"],
            "write_selectors": ["scope:dialogue"],
            "external_effect_selectors": [],
        },
        "bounded_judgment": [{
            "judgment_id": "management-interview-boundary",
            "node_id": INTERVIEW_NODE_ID,
            "verified_circumstances": [
                "The exact Dialogue and governing Process Run identities match."
            ],
            "question": "Is the next question unresolved and materially consequential?",
            "permitted_conclusions": [
                "ask_unresolved_question", "interview_complete", "required_input_unavailable"
            ],
            "permitted_directives": ["ESCALATE", "BLOCKED"],
            "permitted_actions": ["elicit_programming_intent"],
            "authority_grant_ids": ["grant-dialogue"],
            "artifact_selectors": ["scope:dialogue"],
            "required_evidence_ids": ["ev-intent"],
            "evaluator_boundary": "management-interview-question-boundary",
            "stop_conditions": [
                "all_dimensions_resolved", "dialogue_binding_invalid", "principal_cancelled"
            ],
            "return_node_id": INTERVIEW_NODE_ID,
            "escalation_request_types": ["management_input", "scope_clarification"],
        }],
        "evidence": {
            "requirements": [{
                "evidence_id": "ev-intent",
                "claim": "The management intent is bound to the exact Dialogue and Run.",
                "method": "principal_dialogue_answers",
                "producer_independence": "external",
                "artifact_selectors": ["scope:dialogue"],
                "freshness_seconds": 0,
                "required": True,
            }],
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "recapture",
        },
        "correction_loop": {
            "max_attempts": 1,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": 1,
            "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
            "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
        },
        "continuation": {
            "checkpoint_id": "management-interview-entry",
            "resume_node_id": INTERVIEW_NODE_ID,
            "required_state_fields": ["current_node_id", "last_sequence", "artifact_ids"],
            "child_return_fields": [],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": "checkpoint:management-interview-entry",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": ["ev-intent"],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": [
                "interview_complete", "principal_cancelled", "phase_boundary_reached"
            ],
            "blocked_conditions": [
                "required_input_unavailable", "dialogue_binding_invalid"
            ],
            "authority_request_types": ["management_input", "scope_clarification"],
            "authority_return_target": principal_id,
        },
    }


def _process_run(
    *,
    run_id: str,
    definition: Mapping[str, Any],
    dialogue_ref: str,
    route: Mapping[str, Any],
    principal_id: str,
    now: str,
) -> dict[str, Any]:
    return {
        "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_run",
        "run_id": run_id,
        "definition_ref": _definition_ref(definition),
        "state": "ready",
        "entrypoint": ENTRYPOINT,
        "current_node_id": str(definition["graph"]["entry_node_id"]),
        "input_bindings": {
            "entrypoint": ENTRYPOINT,
            "objective": route["objective"],
            "project_ref": route["project_ref"],
            "target_artifact_selectors": ["scope:dialogue", "scope:declared_inputs"],
            "requested_authority_grants": [],
            "dialogue_ref": dialogue_ref,
        },
        "contracts": _interview_contracts(
            run_id=run_id,
            principal_id=principal_id,
            approved_at=now,
            entry_contract_digest=str(route["contract_digest"]),
        ),
        "relationships": {
            "parent_run_id": None,
            "invoked_by_run_id": None,
            "invoked_definition_refs": [],
            "constructed_definition_refs": [],
            "return_to_run_id": None,
        },
        "artifact_ids": [],
        "last_sequence": 0,
        "created_at": now,
        "updated_at": now,
        "labels": ["management-interview", "phase-2.2"],
    }


class ManagementInterviewService:
    """Create, resume, and fold one persistent interview per Dialogue."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        sessions_root: str | Path | None = None,
        repository_root: str | Path | None = None,
        now: Callable[[], str] | None = None,
    ):
        self.runtime = runtime or GovernedProcessRuntime()
        self.sessions_root = Path(sessions_root) if sessions_root is not None else None
        self.repository_root = Path(repository_root) if repository_root is not None else None
        self._now = now or _utc_now

    def _load_definition(self) -> dict[str, Any]:
        return load_programming_definition(self.repository_root)

    def _load_bound_context(
        self,
        dialogue_ref: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
        binding = load_governing_process_binding(
            dialogue_ref,
            sessions_root=self.sessions_root,
        )
        if binding is None:
            return None
        try:
            run = self.runtime.load_run(binding["run_id"])
            stored_definition = self.runtime.load_definition(binding["run_id"])
        except (RunNotFoundError, GovernedRuntimeError) as exc:
            raise ManagementInterviewIntegrityError(
                "Dialogue points to an unavailable or invalid governing Process Run"
            ) from exc
        authoritative = self._load_definition()
        expected_ref = _definition_ref(authoritative)
        expected_digest = _binding_digest(dialogue_ref, run["run_id"], expected_ref)
        if (
            binding["definition_ref"] != expected_ref
            or binding["binding_digest"] != expected_digest
            or run["definition_ref"] != expected_ref
            or run["input_bindings"].get("dialogue_ref") != dialogue_ref
            or stored_definition != authoritative
        ):
            raise ManagementInterviewIntegrityError(
                "Dialogue, Run, and Programming definition identities do not agree"
            )
        if run["state"] != "running" or run["current_node_id"] != INTERVIEW_NODE_ID:
            raise ManagementInterviewConflict(
                "governing Process Run is not at the Phase 2.2 interview boundary"
            )
        return binding, run, authoritative

    def get_state(self, dialogue_ref: str) -> dict[str, Any] | None:
        """Return the folded persistent interview, or ``None`` if unbound."""

        with _SERVICE_LOCK:
            context = self._load_bound_context(dialogue_ref)
            if context is None:
                return None
            binding, run, _definition = context
            state = self._fold_state(dialogue_ref, binding, run)
            # If a process stopped after the final answer append but before the
            # deterministic completion append, finish only that metadata step.
            # No question, plan, authority, or external effect is replayed.
            if not state["unresolved_dimensions"] and state["status"] == "interviewing":
                self.runtime._record_dialogue_observation(
                    state["run_id"],
                    dialogue_ref=dialogue_ref,
                    binding_digest=state["binding_digest"],
                    observation_type="management_interview_completed",
                    payload={
                        "schema_version": INTERVIEW_SCHEMA_VERSION,
                        "answers_digest": state["answers_digest"],
                    },
                )
                run = self.runtime.load_run(state["run_id"])
                state = self._fold_state(dialogue_ref, binding, run)
            return state

    def start_or_resume(
        self,
        dialogue_ref: str,
        route_contract: Mapping[str, Any],
        *,
        principal_id: str = "principal:user",
        dialogue_tag: str = "",
    ) -> dict[str, Any]:
        """Create one governing Run or idempotently resume its interview."""

        dialogue = str(dialogue_ref or "").strip()
        if not dialogue:
            raise ManagementInterviewError("dialogue_ref must be non-empty")
        if dialogue_tag == "stealth":
            raise ManagementInterviewConflict(
                "persistent governed construction is unavailable in a Stealth Dialogue"
            )
        route = _validate_route_contract(route_contract)
        definition = self._load_definition()
        definition_ref = _definition_ref(definition)
        if route.get("definition_ref") not in (None, definition_ref):
            raise ManagementInterviewIntegrityError(
                "construction route names a definition other than the issued Programming identity"
            )
        run_id = _run_id(
            dialogue,
            str(route["project_ref"]),
            str(route["objective"]),
            definition_ref,
        )
        binding_digest = _binding_digest(dialogue, run_id, definition_ref)
        now = self._now()
        binding = {
            "schema_version": BINDING_SCHEMA_VERSION,
            "run_id": run_id,
            "definition_ref": definition_ref,
            "binding_digest": binding_digest,
            "bound_at": now,
        }

        with _SERVICE_LOCK:
            existing = load_governing_process_binding(
                dialogue,
                sessions_root=self.sessions_root,
            )
            if existing is not None:
                if existing["run_id"] != run_id:
                    raise ManagementInterviewConflict(
                        "Dialogue already has a different governing Process Run"
                    )
                state = self.get_state(dialogue)
                if state is None:
                    raise ManagementInterviewIntegrityError(
                        "Dialogue binding disappeared during interview resume"
                    )
                if state["entry_contract_digest"] != route["contract_digest"]:
                    raise ManagementInterviewConflict(
                        "construction route differs from the active governing Run"
                    )
                return state

            envelope = load_conversation_json(
                dialogue,
                sessions_root=self.sessions_root,
            )
            if envelope is not None and envelope.get("tag") == "stealth":
                raise ManagementInterviewConflict(
                    "persistent governed construction is unavailable in a Stealth Dialogue"
                )
            envelope_path = ensure_conversation_envelope(
                dialogue,
                tag=dialogue_tag,
                project_ids=[str(route["project_ref"])],
                sessions_root=self.sessions_root,
            )
            if envelope_path is None:
                raise ManagementInterviewIntegrityError(
                    "Dialogue envelope could not be persisted before Run creation"
                )

            run = _process_run(
                run_id=run_id,
                definition=definition,
                dialogue_ref=dialogue,
                route=route,
                principal_id=principal_id,
                now=now,
            )
            try:
                self.runtime.create_run(definition, run)
            except RunConflictError:
                persisted = self.runtime.load_run(run_id)
                if (
                    persisted["definition_ref"] != run["definition_ref"]
                    or persisted["input_bindings"] != run["input_bindings"]
                ):
                    raise ManagementInterviewIntegrityError(
                        "deterministic management Run identity resolved to different content"
                    )
            self._position_at_interview(run_id)
            try:
                bind_governing_process(
                    dialogue,
                    binding,
                    sessions_root=self.sessions_root,
                )
            except ConversationProcessBindingError as exc:
                raise ManagementInterviewConflict(str(exc)) from exc

            records = self._interview_records(run_id, dialogue, binding_digest)
            if not any(item["observation_type"] == "management_interview_started"
                       for item in records):
                self.runtime._record_dialogue_observation(
                    run_id,
                    dialogue_ref=dialogue,
                    binding_digest=binding_digest,
                    observation_type="management_interview_started",
                    payload={
                        "schema_version": INTERVIEW_SCHEMA_VERSION,
                        "interview_id": f"interview:{run_id}",
                        "route_contract_digest": route["contract_digest"],
                        "project_ref": route["project_ref"],
                        "dimensions": list(INTERVIEW_DIMENSIONS),
                        "initial_answers": _initial_answers(route),
                    },
                )
            state = self.get_state(dialogue)
            if state is None:
                raise ManagementInterviewIntegrityError(
                    "management interview was not recoverable after creation"
                )
            return state

    def _position_at_interview(self, run_id: str) -> None:
        run = self.runtime.load_run(run_id)
        if run["state"] == "created":
            self.runtime.mark_run_ready(
                run_id,
                reason="The principal confirmed the nonmutating management interview.",
            )
            run = self.runtime.load_run(run_id)
        if run["state"] == "ready":
            self.runtime.start_run(
                run_id,
                reason="Begin the confirmed Dialogue-bound management interview.",
            )
            run = self.runtime.load_run(run_id)
        if run["state"] == "running" and run["current_node_id"] == "entry-route":
            self.runtime.advance_decision(
                run_id,
                ENTRYPOINT,
                reason="Construction enters Programming through PRG-Run.",
            )
            run = self.runtime.load_run(run_id)
        if run["state"] != "running" or run["current_node_id"] != INTERVIEW_NODE_ID:
            raise ManagementInterviewConflict(
                "governing Run cannot resume at the management interview node"
            )

    def _interview_records(
        self,
        run_id: str,
        dialogue_ref: str,
        binding_digest: str,
    ) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for record in self.runtime.load_records(run_id):
            event = record.get("event") or {}
            if event.get("event_type") != OBSERVATION_EVENT_TYPE:
                continue
            details = event.get("details") or {}
            payload = details.get("payload")
            if (
                details.get("dialogue_ref") != dialogue_ref
                or details.get("binding_digest") != binding_digest
                or not isinstance(payload, dict)
                or details.get("payload_digest") != _digest_json(payload)
            ):
                raise ManagementInterviewIntegrityError(
                    "Dialogue observation identity or content digest is invalid"
                )
            observations.append({
                "record_id": record["record_id"],
                "recorded_at": record["recorded_at"],
                "observation_type": details.get("observation_type"),
                "payload": copy.deepcopy(payload),
            })
        return observations

    def _fold_state(
        self,
        dialogue_ref: str,
        binding: Mapping[str, Any],
        run: Mapping[str, Any],
    ) -> dict[str, Any]:
        records = self._interview_records(
            run["run_id"], dialogue_ref, str(binding["binding_digest"])
        )
        starts = [item for item in records
                  if item["observation_type"] == "management_interview_started"]
        if len(starts) != 1:
            raise ManagementInterviewIntegrityError(
                "management interview must have exactly one start observation"
            )
        start = starts[0]
        payload = start["payload"]
        if (
            set(payload) != {
                "schema_version", "interview_id", "route_contract_digest",
                "project_ref", "dimensions", "initial_answers",
            }
            or payload.get("schema_version") != INTERVIEW_SCHEMA_VERSION
            or payload.get("interview_id") != f"interview:{run['run_id']}"
            or payload.get("dimensions") != list(INTERVIEW_DIMENSIONS)
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(payload.get("route_contract_digest") or ""),
            )
            or (
                f"Bind exact Phase 2.1 entry contract "
                f"{payload.get('route_contract_digest')}."
                not in run["contracts"]["approved_plan"]["constraints"]
            )
            or payload.get("project_ref") != run["input_bindings"].get("project_ref")
            or not isinstance(payload.get("initial_answers"), dict)
        ):
            raise ManagementInterviewIntegrityError(
                "management interview start observation is invalid"
            )
        answers: dict[str, dict[str, Any]] = {}
        for dimension, fact in payload["initial_answers"].items():
            if dimension not in INTERVIEW_DIMENSIONS or not isinstance(fact, dict):
                raise ManagementInterviewIntegrityError("initial interview answer is invalid")
            answer = str(fact.get("answer") or "").strip()
            source = str(fact.get("source") or "").strip()
            if not answer or not source:
                raise ManagementInterviewIntegrityError("initial interview answer is empty")
            # Runs created before the tightened Phase 2.2 gate may contain an
            # authenticated but semantically vague initial fact.  It remains
            # part of history, but cannot resolve the dimension.
            if not _materially_resolves(dimension, answer):
                continue
            answers[dimension] = {
                "answer": answer,
                "source": source,
                "record_id": start["record_id"],
                "recorded_at": start["recorded_at"],
            }

        temporary_calls: dict[str, dict[str, Any]] = {}
        answer_receipts: dict[str, dict[str, str]] = {}
        completion_records: list[dict[str, Any]] = []
        for item in records:
            kind = item["observation_type"]
            item_payload = item["payload"]
            if kind == "management_interview_answered":
                legacy_keys = {
                    "schema_version", "question_id", "dimension", "answer", "source",
                }
                if set(item_payload) == legacy_keys:
                    # Legacy non-idempotent observations cannot resolve a
                    # dimension under the corrected interview contract.
                    continue
                dimension = str(item_payload.get("dimension") or "")
                answer = str(item_payload.get("answer") or "").strip()
                source = str(item_payload.get("source") or "").strip()
                question_id = str(item_payload.get("question_id") or "")
                idempotency_key = str(item_payload.get("idempotency_key") or "")
                response = " ".join(str(item_payload.get("response") or "").split())
                response_digest = str(item_payload.get("response_digest") or "")
                expected_response_digest = _digest_json({"answer": response})
                unresolved_before = [
                    candidate for candidate in INTERVIEW_DIMENSIONS
                    if candidate not in answers
                ]
                expected_question_id = (
                    f"question:{run['run_id']}:{unresolved_before[0]}"
                    if unresolved_before else ""
                )
                receipt = answer_receipts.get(idempotency_key)
                if (
                    set(item_payload) != {
                        "schema_version", "question_id", "idempotency_key",
                        "response", "response_digest", "dimension", "answer", "source",
                    }
                    or item_payload.get("schema_version") != INTERVIEW_SCHEMA_VERSION
                    or dimension not in INTERVIEW_DIMENSIONS
                    or dimension in answers
                    or not answer
                    or not source
                    or not re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", idempotency_key
                    )
                    or not response
                    or response_digest != expected_response_digest
                    or not _materially_resolves(dimension, answer)
                ):
                    raise ManagementInterviewIntegrityError(
                        "management interview answer observation is invalid or duplicated"
                    )
                if receipt is None:
                    if (
                        not unresolved_before
                        or dimension != unresolved_before[0]
                        or question_id != expected_question_id
                    ):
                        raise ManagementInterviewIntegrityError(
                            "management interview answer does not bind the pending question"
                        )
                    receipt = {
                        "question_id": question_id,
                        "response_digest": response_digest,
                    }
                    answer_receipts[idempotency_key] = receipt
                elif (
                    receipt["question_id"] != question_id
                    or receipt["response_digest"] != response_digest
                ):
                    raise ManagementInterviewIntegrityError(
                        "management interview idempotency identity was reused"
                    )
                answers[dimension] = {
                    "answer": answer,
                    "source": source,
                    "question_id": question_id,
                    "idempotency_key": idempotency_key,
                    "response": response,
                    "response_digest": response_digest,
                    "record_id": item["record_id"],
                    "recorded_at": item["recorded_at"],
                }
            elif kind == "temporary_framework_started":
                call_id = str(item_payload.get("call_id") or "")
                framework_id = str(item_payload.get("framework_id") or "")
                unresolved_at_call = [
                    dimension for dimension in INTERVIEW_DIMENSIONS
                    if dimension not in answers
                ]
                expected_question = (
                    f"question:{run['run_id']}:{unresolved_at_call[0]}"
                    if unresolved_at_call else None
                )
                if (
                    set(item_payload) != {
                        "schema_version", "call_id", "framework_id", "request_digest",
                        "pending_question_id",
                    }
                    or item_payload.get("schema_version") != INTERVIEW_SCHEMA_VERSION
                    or not call_id
                    or not framework_id
                    or call_id in temporary_calls
                    or not re.fullmatch(
                        r"sha256:[0-9a-f]{64}",
                        str(item_payload.get("request_digest") or ""),
                    )
                    or item_payload.get("pending_question_id") != expected_question
                ):
                    raise ManagementInterviewIntegrityError(
                        "temporary framework start observation is invalid"
                    )
                temporary_calls[call_id] = {
                    "call_id": call_id,
                    "framework_id": framework_id,
                    "request_digest": item_payload.get("request_digest"),
                    "status": "running",
                    "started_record_id": item["record_id"],
                }
            elif kind == "temporary_framework_completed":
                call_id = str(item_payload.get("call_id") or "")
                call = temporary_calls.get(call_id)
                if (
                    set(item_payload) != {
                        "schema_version", "call_id", "status", "result_ref",
                    }
                    or item_payload.get("schema_version") != INTERVIEW_SCHEMA_VERSION
                    or call is None
                    or call["status"] != "running"
                    or item_payload.get("status") not in {"ok", "errored", "blocked"}
                    or not isinstance(item_payload.get("result_ref"), dict)
                ):
                    raise ManagementInterviewIntegrityError(
                        "temporary framework completion lacks one active call"
                    )
                call["status"] = str(item_payload.get("status") or "")
                call["result_ref"] = copy.deepcopy(item_payload.get("result_ref"))
                call["completed_record_id"] = item["record_id"]
            elif kind == "management_interview_completed":
                completion_records.append(item)
            elif kind != "management_interview_started":
                raise ManagementInterviewIntegrityError(
                    f"unknown management interview observation: {kind!r}"
                )

        unresolved = [item for item in INTERVIEW_DIMENSIONS if item not in answers]
        answers_digest = _digest_json({
            dimension: answers[dimension]["answer"]
            for dimension in INTERVIEW_DIMENSIONS
            if dimension in answers
        })
        if len(completion_records) > 1:
            raise ManagementInterviewIntegrityError(
                "management interview has duplicate completion observations"
            )
        if completion_records:
            completion = completion_records[0]["payload"]
            if (
                set(completion) != {"schema_version", "answers_digest"}
                or unresolved
                or completion.get("schema_version") != INTERVIEW_SCHEMA_VERSION
                or completion.get("answers_digest") != answers_digest
            ):
                raise ManagementInterviewIntegrityError(
                    "management interview completion does not bind the exact answers"
                )
        status = "ready_for_plan" if completion_records else "interviewing"
        ordered_answers = {
            dimension: answers[dimension]
            for dimension in INTERVIEW_DIMENSIONS
            if dimension in answers
        }
        current_question = None
        if unresolved:
            dimension = unresolved[0]
            current_question = {
                "question_id": f"question:{run['run_id']}:{dimension}",
                "dimension": dimension,
                **copy.deepcopy(_QUESTIONS[dimension]),
            }
        return {
            "schema_version": INTERVIEW_SCHEMA_VERSION,
            "interview_id": payload["interview_id"],
            "dialogue_ref": dialogue_ref,
            "run_id": run["run_id"],
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "binding_digest": binding["binding_digest"],
            "project_ref": run["input_bindings"]["project_ref"],
            "entry_contract_digest": payload["route_contract_digest"],
            "status": status,
            "answers": ordered_answers,
            "answers_digest": answers_digest,
            "unresolved_dimensions": unresolved,
            "current_question": current_question,
            "temporary_framework_calls": list(temporary_calls.values()),
            "next_action": (
                "await_management_answer" if unresolved else "await_phase_2_3_plan"
            ),
            "creates_plan": False,
            "authority_effects": [],
        }

    def answer(
        self,
        dialogue_ref: str,
        answer: str,
        *,
        question_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Bind one material principal answer to one exact pending question."""

        normalized = " ".join(str(answer or "").split())
        if not normalized:
            raise ManagementInterviewError("management interview answer must be non-empty")
        if len(normalized) > 20_000:
            raise ManagementInterviewError("management interview answer is too long")
        supplied_question_id = str(question_id or "").strip()
        answer_key = _normalize_answer_idempotency_key(
            idempotency_key
            or _default_answer_idempotency_key(dialogue_ref, normalized)
        )
        response_digest = _digest_json({"answer": normalized})
        with _SERVICE_LOCK:
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ManagementInterviewConflict("Dialogue has no active management interview")
            prior = [
                fact for fact in state["answers"].values()
                if fact.get("idempotency_key") == answer_key
            ]
            if prior:
                prior_questions = {fact.get("question_id") for fact in prior}
                prior_digests = {fact.get("response_digest") for fact in prior}
                if (
                    prior_digests != {response_digest}
                    or (
                        supplied_question_id
                        and prior_questions != {supplied_question_id}
                    )
                ):
                    raise ManagementInterviewConflict(
                        "management answer idempotency identity conflicts with its receipt"
                    )
                # This exact answer was already made authoritative.  Return the
                # folded state even if the Dialogue save failed after append;
                # never reinterpret it as an answer to the next question.
                return state
            question = state["current_question"]
            if state["status"] != "interviewing" or question is None:
                raise ManagementInterviewConflict("management interview is already complete")
            if supplied_question_id and supplied_question_id != question["question_id"]:
                raise ManagementInterviewConflict(
                    "management answer does not name the current pending question"
                )
            facts = _explicit_answers(normalized, source_prefix="principal")
            current_fact = facts.get(question["dimension"]) or {
                "answer": normalized,
                "source": "principal_dialogue_answer",
            }
            if not _materially_resolves(question["dimension"], current_fact["answer"]):
                required = copy.deepcopy(state)
                required["status"] = "input_required"
                required["next_action"] = "provide_management_answer"
                required["input_required"] = {
                    "type": "management_interview_input_required",
                    "question_id": question["question_id"],
                    "dimension": question["dimension"],
                    "idempotency_key": answer_key,
                    "reason": "The response does not materially resolve the pending dimension.",
                }
                return required
            answer_dimensions = [question["dimension"]]
            answer_dimensions.extend(
                dimension for dimension in INTERVIEW_DIMENSIONS
                if dimension in facts
                and dimension in state["unresolved_dimensions"]
                and dimension != question["dimension"]
            )
            for dimension in answer_dimensions:
                fact = current_fact if dimension == question["dimension"] else facts[dimension]
                self.runtime._record_dialogue_observation(
                    state["run_id"],
                    dialogue_ref=dialogue_ref,
                    binding_digest=state["binding_digest"],
                    observation_type="management_interview_answered",
                    payload={
                        "schema_version": INTERVIEW_SCHEMA_VERSION,
                        "question_id": question["question_id"],
                        "idempotency_key": answer_key,
                        "response": normalized,
                        "response_digest": response_digest,
                        "dimension": dimension,
                        "answer": fact["answer"],
                        "source": fact["source"],
                    },
                )
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ManagementInterviewIntegrityError("interview disappeared after answer")
            return state

    def begin_temporary_framework_call(
        self,
        dialogue_ref: str,
        framework_id: str,
        request_text: str,
    ) -> dict[str, Any]:
        """Record an analytical call without changing the pending interview."""

        framework = str(framework_id or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", framework):
            raise ManagementInterviewError("temporary framework_id is invalid")
        if framework == "programming":
            raise ManagementInterviewConflict(
                "Programming cannot replace its own governing interview as a temporary call"
            )
        if (
            not is_user_pickable_framework(framework)
            or is_process_definition_framework(framework)
        ):
            raise ManagementInterviewError(
                "temporary framework is not an available analytical framework"
            )
        state = self.get_state(dialogue_ref)
        if state is None or state["status"] != "interviewing":
            raise ManagementInterviewConflict("Dialogue has no active management interview")
        call_id = f"framework-call:{uuid.uuid4().hex}"
        self.runtime._record_dialogue_observation(
            state["run_id"],
            dialogue_ref=dialogue_ref,
            binding_digest=state["binding_digest"],
            observation_type="temporary_framework_started",
            payload={
                "schema_version": INTERVIEW_SCHEMA_VERSION,
                "call_id": call_id,
                "framework_id": framework,
                "request_digest": _digest_json(str(request_text or "")),
                "pending_question_id": state["current_question"]["question_id"],
            },
        )
        resumed = self.get_state(dialogue_ref)
        if resumed is None:
            raise ManagementInterviewIntegrityError("interview disappeared during temporary call")
        return {
            "call_id": call_id,
            "run_id": resumed["run_id"],
            "pending_question": copy.deepcopy(resumed["current_question"]),
        }

    def complete_temporary_framework_call(
        self,
        dialogue_ref: str,
        call_id: str,
        *,
        status: str,
        result_ref: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return from an analytical call to the unchanged interview question."""

        if status not in {"ok", "errored", "blocked"}:
            raise ManagementInterviewError("temporary framework status is invalid")
        state = self.get_state(dialogue_ref)
        if state is None or state["status"] != "interviewing":
            raise ManagementInterviewConflict("Dialogue has no active management interview")
        active = [
            item for item in state["temporary_framework_calls"]
            if item["call_id"] == call_id and item["status"] == "running"
        ]
        if len(active) != 1:
            raise ManagementInterviewConflict("temporary framework call is not active")
        self.runtime._record_dialogue_observation(
            state["run_id"],
            dialogue_ref=dialogue_ref,
            binding_digest=state["binding_digest"],
            observation_type="temporary_framework_completed",
            payload={
                "schema_version": INTERVIEW_SCHEMA_VERSION,
                "call_id": call_id,
                "status": status,
                "result_ref": copy.deepcopy(dict(result_ref)),
            },
        )
        resumed = self.get_state(dialogue_ref)
        if resumed is None:
            raise ManagementInterviewIntegrityError("interview disappeared after temporary call")
        return resumed


__all__ = [
    "INTERVIEW_DIMENSIONS",
    "INTERVIEW_SCHEMA_VERSION",
    "ManagementInterviewConflict",
    "ManagementInterviewError",
    "ManagementInterviewIntegrityError",
    "ManagementInterviewService",
]
