"""Ora-native entry and routing contracts for governed work.

Phase 2.1 stops at a verified, authority-neutral routing decision.  It does
not create a Process Run, begin the persistent management interview, approve a
plan, invoke a definition, or activate anything.  Those effects belong to
later gated phases.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    import process_contracts as _contracts
    from active_project import canonicalize_project_nexus
    from framework_invocability import (
        is_process_definition_framework,
        is_user_pickable_framework,
        load_framework_invocability_registry,
    )
    from process_definition_registry import (
        DefinitionIntegrityError,
        ProcessDefinitionRegistry,
    )
except ImportError:  # pragma: no cover - package-qualified imports
    from orchestrator import process_contracts as _contracts
    from orchestrator.active_project import canonicalize_project_nexus
    from orchestrator.framework_invocability import (
        is_process_definition_framework,
        is_user_pickable_framework,
        load_framework_invocability_registry,
    )
    from orchestrator.process_definition_registry import (
        DefinitionIntegrityError,
        ProcessDefinitionRegistry,
    )


ENTRY_SCHEMA_VERSION = "ora.process-entry/1.0"
ENTRY_SOURCES = frozenset({
    "inquiry",
    "construction_action",
    "shared_picker",
    "process_library",
    "natural_language",
})
ENTRY_INTENTS = frozenset({
    "ordinary_generation",
    "capability_invocation",
    "capability_construction",
    "capability_activation",
})
ENTRY_STATUSES = frozenset({
    "ready",
    "awaiting_project_confirmation",
    "awaiting_definition_selection",
    "awaiting_activation",
})
_REQUEST_FIELDS = frozenset({
    "source",
    "objective",
    "project_ref",
    "project_confirmed",
    "selected_definition_ref",
    "selected_framework_id",
})
_DEFINITION_REF_FIELDS = frozenset({"definition_id", "version", "digest"})
_PROGRAMMING_MARKER = re.compile(
    r"<!-- PROGRAMMING_PROCESS_DEFINITION_BEGIN -->\n"
    r"```json\n(.*?)\n```\n"
    r"<!-- PROGRAMMING_PROCESS_DEFINITION_END -->",
    flags=re.DOTALL,
)
_REPO_ROOT = Path(__file__).resolve().parents[1]


class ProcessEntryRoutingError(ValueError):
    """Raised when an entry request or selected definition is invalid."""


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _section_first_paragraph(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return ""
    return re.split(r"\n\s*\n", match.group(1).strip(), maxsplit=1)[0].strip()


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def load_programming_definition(
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load and authenticate the exact issued Programming definition.

    The operational mirror is never trusted on file presence or its declared
    identity alone.  The same content-identity verifier used by registry
    registration and resolution checks it against the authoritative canonical
    body and embedded projection on every read.
    """

    root = Path(repository_root or _REPO_ROOT).resolve()
    path = root / "frameworks" / "book" / "programming.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DefinitionIntegrityError(
            f"Programming Process Definition mirror is unavailable: {path}"
        ) from exc
    match = _PROGRAMMING_MARKER.search(text)
    if match is None:
        raise DefinitionIntegrityError(
            "Programming mirror lacks its embedded Process Definition"
        )
    try:
        raw_definition = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise DefinitionIntegrityError(
            "Programming mirror contains an invalid Process Definition projection"
        ) from exc
    definition = _contracts.validate_process_definition(raw_definition)
    ProcessDefinitionRegistry._verify_issued_content_identity(definition)
    return definition


def load_programming_entry(
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return the authenticated Programming definition's entry projection."""

    root = Path(repository_root or _REPO_ROOT).resolve()
    path = root / "frameworks" / "book" / "programming.md"
    text = path.read_text(encoding="utf-8")
    definition = load_programming_definition(root)
    return {
        "kind": "process_definition",
        "id": "programming",
        "display_name": _section_first_paragraph(text, "Display Name") or definition["title"],
        "display_description": (
            _section_first_paragraph(text, "Display Description")
            or definition["purpose"]
        ),
        "category": "process-definition",
        "definition_ref": _definition_ref(definition),
        "scope": copy.deepcopy(definition["scope"]),
        "status": definition["status"],
        "entrypoints": copy.deepcopy(
            definition["input_schema"]["properties"]["entrypoint"]["enum"]
        ),
        "activated": False,
        "aliases": ["programming", "governed programming", "ora programming", "prg"],
    }


def list_entry_definitions(
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return authenticated definitions available to Phase 2.1 entry routes."""

    return [load_programming_entry(repository_root)]


def _normalize_definition_ref(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != _DEFINITION_REF_FIELDS:
        raise ProcessEntryRoutingError(
            "selected_definition_ref must contain exact definition_id, version, and digest"
        )
    normalized = {key: str(value[key]).strip() for key in _DEFINITION_REF_FIELDS}
    if not all(normalized.values()):
        raise ProcessEntryRoutingError(
            "selected_definition_ref values must be non-empty"
        )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized["digest"]):
        raise ProcessEntryRoutingError(
            "selected_definition_ref digest must be lowercase sha256"
        )
    return normalized


def _catalog_by_ref(
    catalog: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for entry in catalog:
        ref = _normalize_definition_ref(entry.get("definition_ref"))
        if ref is None:
            raise ProcessEntryRoutingError("entry catalog contains a definition without identity")
        result[(ref["definition_id"], ref["version"], ref["digest"])] = entry
    return result


def _find_named_definition(
    objective: str,
    catalog: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    lowered = objective.casefold()
    matches: list[Mapping[str, Any]] = []
    for entry in catalog:
        tokens = {
            str(entry.get("id") or "").casefold(),
            str(entry.get("display_name") or "").casefold(),
            str((entry.get("definition_ref") or {}).get("definition_id") or "").casefold(),
            *(str(alias).casefold() for alias in entry.get("aliases") or []),
        }
        if any(token and re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", lowered)
               for token in tokens):
            matches.append(entry)
    return matches[0] if len(matches) == 1 else None


def _find_named_framework(objective: str) -> str | None:
    """Resolve one curated legacy framework named in ordinary language."""

    lowered = objective.casefold()
    matches: set[str] = set()
    registry = load_framework_invocability_registry()
    for token, filename in registry.invocable_by_key.items():
        words = [re.escape(part) for part in re.split(r"[-_\s]+", token) if part]
        if not words:
            continue
        pattern = r"(?<![\w-])" + r"[\s_-]+".join(words) + r"(?![\w-])"
        if re.search(pattern, lowered):
            matches.add(Path(filename).stem)
    return next(iter(matches)) if len(matches) == 1 else None


_CAPABILITY_NOUN = (
    r"(?:capabilit(?:y|ies)|process(?:es)?|framework(?:s)?|workflow(?:s)?|"
    r"automation(?:s)?|tool(?:s)?|script(?:s)?|program(?:s)?|app(?:lication)?s?|"
    r"integration(?:s)?|service(?:s)?)"
)
_ACTIVATION_RE = re.compile(
    rf"\b(?:activate|enable|deploy|publish|schedule|turn\s+on)\b"
    rf"(?:\s+\w+){{0,5}}\s+{_CAPABILITY_NOUN}\b",
    flags=re.IGNORECASE,
)
_REUSABLE_CONSTRUCTION_RE = re.compile(
    rf"\b(?:build|create|construct|design|formalize|modify|change|update|replace)\b"
    rf"(?:\s+\w+){{0,7}}\s+{_CAPABILITY_NOUN}\b|"
    r"\b(?:reusable|repeatable|standing)\b(?:\s+\w+){0,5}\s+"
    rf"(?:{_CAPABILITY_NOUN}|spreadsheet|workbook|template)\b",
    flags=re.IGNORECASE,
)
_PROGRAMMING_CHANGE_RE = re.compile(
    r"\b(?:add|build|change|debug|fix|implement|modify|refactor|remove|update)\b"
    r"(?:\s+\w+){0,8}\s+"
    r"(?:api|app|bug|class|code|feature|file|function|integration|package|repo(?:sitory)?|"
    r"script|server|test|\.\w{1,8})\b",
    flags=re.IGNORECASE,
)
_INVOCATION_RE = re.compile(
    rf"\b(?:apply|execute|invoke|run|use)\b(?:\s+\w+){{0,6}}\s+{_CAPABILITY_NOUN}\b",
    flags=re.IGNORECASE,
)
_MANAGED_WORK_ACTION = (
    r"(?:alert|archive|back\s+up|calculate|check|compile|create|deliver|email|export|"
    r"generate|import|inspect|monitor|notify|prepare|process|produce|reconcile|refresh|"
    r"review|run|send|summarize|sync|update|validate|verify)"
)
_REQUEST_LEAD = (
    r"(?:"
    r"(?:(?:please|kindly)\s+)?|"
    r"(?:can|could|would|will)\s+you\s+(?:(?:please|kindly)\s+)?|"
    r"i\s+(?:need|want)(?:\s+you)?\s+to\s+"
    r")"
)
_CONTENT_ABOUT_WORK_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:describe|explain|summarize)\b|"
    rf"^\s*{_REQUEST_LEAD}(?:analy[sz]e|assess|check|review)\b.{{0,100}}"
    r"\b(?:documentation|docs?|framework|definition|guide|how|what|whether|why)\b|"
    rf"^\s*{_REQUEST_LEAD}(?:create|draft|prepare|produce|write)\b.{{0,60}}"
    r"\b(?:documentation|docs?|explanation|guide|overview|summary|tutorial)\b|"
    r"^\s*(?:how|what|why|where)\b|"
    r"^\s*(?:can|could|should|would)\s+i\b|"
    r"^\s*(?:show|tell)\s+me\b.{0,80}\b(?:how|what|whether|why)\b",
    flags=re.IGNORECASE,
)
_AUTOMATION_REQUEST_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}automate\b|"
    rf"^\s*{_REQUEST_LEAD}make\b.{{0,80}}\bautomatic(?:ally)?\b|"
    rf"^\s*{_REQUEST_LEAD}automatically\b.{{0,80}}\b{_MANAGED_WORK_ACTION}\b|"
    rf"^\s*{_REQUEST_LEAD}{_MANAGED_WORK_ACTION}\b.{{0,80}}\bautomatically\b",
    flags=re.IGNORECASE,
)
_MANAGED_WORK_RE = re.compile(
    rf"\b{_MANAGED_WORK_ACTION}\b",
    flags=re.IGNORECASE,
)
_MANAGED_WORK_REQUEST_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}{_MANAGED_WORK_ACTION}\b",
    flags=re.IGNORECASE,
)
_EFFECT_SETUP_REQUEST_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:arrange(?:\s+for|\s+to)?|establish|set\s+up)\b",
    flags=re.IGNORECASE,
)
_REUSABLE_EFFECT_RE = re.compile(
    r"\b(?:ongoing|recurring|repeatable|reusable|standing)\b",
    flags=re.IGNORECASE,
)
_BROAD_CADENCE_RE = re.compile(
    r"\b(?:hourly|daily|nightly|weekly|monthly|quarterly|annually|yearly)\b|"
    r"\b(?:every|each)\s+(?:(?:other|\d+)\s+)?(?:minute|hour|day|night|weekday|"
    r"week|month|quarter|year|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday)s?\b|"
    r"\bon\s+(?:mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)\b",
    flags=re.IGNORECASE,
)
_CADENCE_RE = re.compile(
    r"\b(?:hourly|daily|nightly|weekly|monthly|quarterly|annually|yearly)\b\s*[.!?]*$|"
    r"\b(?:every|each)\s+(?:(?:other|\d+)\s+)?(?:minute|hour|day|night|weekday|"
    r"week|month|quarter|year|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday)s?\b|"
    r"\bon\s+(?:mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)\b",
    flags=re.IGNORECASE,
)
_TRIGGER_RE = re.compile(
    r"\b(?:whenever|every\s+time|each\s+time)\b|"
    r"\bwhen\b.{0,100}\b(?:arrives?|changes?|completes?|fails?|is\s+(?:added|"
    r"created|modified|received|updated))\b",
    flags=re.IGNORECASE,
)
_CADENCE_AT_START_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:"
    r"(?:hourly|daily|nightly|weekly|monthly|quarterly|annually|yearly)\b\s*[:,]|"
    r"(?:every|each)\s+(?:(?:other|\d+)\s+)?(?:minute|hour|day|night|weekday|"
    r"week|month|quarter|year|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday)s?\b|"
    r"on\s+(?:mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)\b)",
    flags=re.IGNORECASE,
)
_TRIGGER_AT_START_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:"
    r"(?:whenever|every\s+time|each\s+time)\b|"
    r"when\b.{0,100}\b(?:arrives?|changes?|completes?|fails?|is\s+(?:added|"
    r"created|modified|received|updated))\b)",
    flags=re.IGNORECASE,
)
_NAMED_ACTIVATION_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:activate|enable|deploy|publish|schedule|turn\s+on)\b",
    flags=re.IGNORECASE,
)
_NAMED_AVAILABILITY_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:make|keep)\b.{{0,80}}"
    r"\b(?:available|usable|accessible|ready\s+for\s+use)\b|"
    rf"^\s*{_REQUEST_LEAD}(?:allow|permit)\b.{{0,80}}\b(?:access|use)\b",
    flags=re.IGNORECASE,
)
_NAMED_CONSTRUCTION_RE = re.compile(
    rf"^\s*{_REQUEST_LEAD}(?:build|construct|create|design|formalize|modify|"
    r"change|update|replace|"
    r"debug|fix|implement|refactor|remove)\b",
    flags=re.IGNORECASE,
)
_NAMED_OPERATOR_ACTION = (
    r"(?:analy[sz]e|apply|assess|check|classify|compare|do|evaluate|execute|handle|"
    r"help|inspect|invoke|map|process|review|run|summarize|take\s+care\s+of|test|"
    r"use|validate|verify|work(?:\s+on)?)"
)
_NAMED_CONTENT_NOUN = r"(?:documentation|docs?|guide|manual|overview|reference)"
_NAMED_CONTENT_SUFFIX = (
    rf"(?!"
    rf"['’]s\b|\s+{_NAMED_CONTENT_NOUN}\b|"
    r"\s+(?:as|for)\s+(?:(?:an?|the)\s+)?"
    r"(?:comparison|example|reference|subject)\b|"
    r"\s+in\s+(?:(?:an?|the|this)\s+)?(?:documentation|docs?|example|guide)\b"
    r")"
)


def _is_recurring_effect_request(objective: str) -> bool:
    """Require a recurring/trigger signal to govern an effect action."""

    if (_EFFECT_SETUP_REQUEST_RE.search(objective)
            and _MANAGED_WORK_RE.search(objective)
            and (_REUSABLE_EFFECT_RE.search(objective)
                 or _BROAD_CADENCE_RE.search(objective)
                 or _TRIGGER_RE.search(objective))):
        return True
    if not (_CADENCE_RE.search(objective) or _TRIGGER_RE.search(objective)):
        return False
    if _MANAGED_WORK_REQUEST_RE.search(objective):
        return True
    signal = _CADENCE_AT_START_RE.search(objective) or _TRIGGER_AT_START_RE.search(
        objective
    )
    return bool(signal and _MANAGED_WORK_RE.search(objective, signal.end()))


def _named_capability_pattern(
    named_entry: Mapping[str, Any] | None,
    named_framework_id: str | None,
) -> str | None:
    """Build the exact language patterns that resolved one named capability."""

    tokens: set[str] = set()
    if named_entry is not None:
        tokens.update({
            str(named_entry.get("id") or ""),
            str(named_entry.get("display_name") or ""),
            str((named_entry.get("definition_ref") or {}).get("definition_id") or ""),
            *(str(alias) for alias in named_entry.get("aliases") or []),
        })
    if named_framework_id is not None:
        tokens.add(named_framework_id)
        registry = load_framework_invocability_registry()
        tokens.update(
            token for token, filename in registry.invocable_by_key.items()
            if Path(filename).stem == named_framework_id
        )
    patterns: list[str] = []
    for token in sorted((token.strip() for token in tokens if token.strip()),
                        key=len, reverse=True):
        parts = [part for part in re.split(r"[-_/\s]+", token) if part]
        if parts:
            core = r"[\s_/-]+".join(re.escape(part) for part in parts)
            patterns.append(rf"(?<![\w-]){core}(?![\w-])")
    return "(?:" + "|".join(patterns) + ")" if patterns else None


def _named_capability_is_operator(
    objective: str,
    named_entry: Mapping[str, Any] | None,
    named_framework_id: str | None,
) -> bool:
    """Recognize the named capability as actor/tool, never mere subject matter."""

    name = _named_capability_pattern(named_entry, named_framework_id)
    if name is None:
        return False
    patterns = (
        rf"^\s*{_REQUEST_LEAD}(?:apply|execute|invoke|run|use)\s+"
        rf"(?:the\s+)?{name}{_NAMED_CONTENT_SUFFIX}",
        rf"^\s*{_REQUEST_LEAD}(?:ask|get|have|let|tell)\b.{{0,40}}{name}"
        rf".{{0,30}}\b(?:to\s+)?{_NAMED_OPERATOR_ACTION}\b",
        rf"^\s*(?:can|could|would|will|should)\s+{name}[,:]?\s+"
        rf"(?:please\s+)?{_NAMED_OPERATOR_ACTION}\b",
        rf"^\s*i\s+(?:need|want)\s+{name}\s+to\s+{_NAMED_OPERATOR_ACTION}\b",
        rf"^\s*(?:please\s+)?{name}[,:]?\s+{_NAMED_OPERATOR_ACTION}\b",
    )
    return any(re.search(pattern, objective, flags=re.IGNORECASE) for pattern in patterns)


def _classify_intent(
    source: str,
    objective: str,
    selected_entry: Mapping[str, Any] | None,
    named_entry: Mapping[str, Any] | None,
    selected_framework_id: str | None,
    named_framework_id: str | None,
) -> tuple[str, list[str]]:
    named_capability = named_entry is not None or named_framework_id is not None
    if source == "construction_action":
        return "capability_construction", ["explicit construction/programming action"]
    if (selected_entry is None and selected_framework_id is None
            and _CONTENT_ABOUT_WORK_RE.search(objective)):
        return "ordinary_generation", ["explanatory or content request about work"]
    if _ACTIVATION_RE.search(objective):
        return "capability_activation", ["activation language with a capability object"]
    if _AUTOMATION_REQUEST_RE.search(objective):
        return "capability_construction", ["explicit automation request"]
    if _is_recurring_effect_request(objective):
        return "capability_construction", ["recurring or triggered work request"]
    if _REUSABLE_CONSTRUCTION_RE.search(objective):
        return "capability_construction", ["construction language with a capability object"]
    if _PROGRAMMING_CHANGE_RE.search(objective):
        return "capability_construction", ["programming artifact mutation language"]
    if named_capability and _NAMED_ACTIVATION_RE.search(objective):
        return "capability_activation", ["activation language with an exact named capability"]
    if named_capability and _NAMED_AVAILABILITY_RE.search(objective):
        return "capability_activation", ["availability request for an exact named capability"]
    if named_capability and _NAMED_CONSTRUCTION_RE.search(objective):
        return "capability_construction", ["construction language with an exact named capability"]
    if selected_entry is not None:
        return "capability_invocation", ["exact Process Definition selected"]
    if selected_framework_id is not None:
        return "capability_invocation", ["curated framework selected"]
    if named_capability and _named_capability_is_operator(
        objective, named_entry, named_framework_id,
    ):
        return "capability_invocation", ["exact named capability is the requested operator"]
    if named_capability:
        return "ordinary_generation", ["named capability is request subject matter"]
    if _INVOCATION_RE.search(objective):
        return "capability_invocation", ["invocation language with a capability object"]
    return "ordinary_generation", ["no reusable-capability or activation boundary detected"]


def route_process_entry(
    request: Mapping[str, Any],
    *,
    catalog: Sequence[Mapping[str, Any]] | None = None,
    project_visible: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Validate and classify one Phase 2.1 entry request.

    The result is a routing contract only.  Its empty ``authority_effects``
    field is deliberate: entry does not grant construction, invocation, or
    activation authority.
    """

    if not isinstance(request, Mapping):
        raise ProcessEntryRoutingError("process entry request must be an object")
    unexpected = set(request) - _REQUEST_FIELDS
    if unexpected:
        raise ProcessEntryRoutingError(
            "unsupported process entry fields: " + ", ".join(sorted(unexpected))
        )
    source = str(request.get("source") or "").strip()
    if source not in ENTRY_SOURCES:
        raise ProcessEntryRoutingError(
            "source must be one of: " + ", ".join(sorted(ENTRY_SOURCES))
        )
    objective = str(request.get("objective") or "").strip()
    if not objective:
        raise ProcessEntryRoutingError("What should happen? must be non-empty")
    raw_confirmed = request.get("project_confirmed", False)
    if not isinstance(raw_confirmed, bool):
        raise ProcessEntryRoutingError("project_confirmed must be boolean")
    project_ref = canonicalize_project_nexus(str(request.get("project_ref") or ""))
    selected_ref = _normalize_definition_ref(request.get("selected_definition_ref"))
    selected_framework_id = str(request.get("selected_framework_id") or "").strip()
    if selected_ref is not None and selected_framework_id:
        raise ProcessEntryRoutingError(
            "select either a Process Definition or a framework, not both"
        )
    if selected_framework_id:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", selected_framework_id):
            raise ProcessEntryRoutingError("selected_framework_id is invalid")
        if (not is_user_pickable_framework(selected_framework_id)
                or is_process_definition_framework(selected_framework_id)):
            raise ProcessEntryRoutingError(
                "selected framework is not available through the shared picker"
            )
    else:
        selected_framework_id = None
    if source == "shared_picker" and selected_ref is None and selected_framework_id is None:
        raise ProcessEntryRoutingError(
            "shared_picker entry requires an exact Process Definition or curated framework"
        )
    if source == "process_library" and selected_ref is None:
        raise ProcessEntryRoutingError(
            "process_library entry requires an exact selected_definition_ref"
        )

    definitions = list(catalog) if catalog is not None else list_entry_definitions()
    by_ref = _catalog_by_ref(definitions)
    selected_entry = None
    if selected_ref is not None:
        key = (
            selected_ref["definition_id"],
            selected_ref["version"],
            selected_ref["digest"],
        )
        selected_entry = by_ref.get(key)
        if selected_entry is None:
            raise ProcessEntryRoutingError(
                "selected Process Definition is not available at that exact identity"
            )
    named_entry = selected_entry or _find_named_definition(objective, definitions)
    named_framework_id = (
        selected_framework_id or _find_named_framework(objective)
    )
    intent, basis = _classify_intent(
        source,
        objective,
        selected_entry,
        named_entry,
        selected_framework_id,
        named_framework_id,
    )
    resolved_framework_id = (
        named_framework_id if intent != "ordinary_generation" else selected_framework_id
    )

    if project_visible is not None and not project_visible(project_ref):
        raise ProcessEntryRoutingError(
            f"project is not available for new governed work: {project_ref}"
        )
    if (
        named_entry is not None
        and intent in {"capability_invocation", "capability_activation"}
    ):
        definition_scope = named_entry.get("scope")
        if (
            not isinstance(definition_scope, Mapping)
            or set(definition_scope) != {"kind", "selector"}
        ):
            raise ProcessEntryRoutingError(
                "selected Process Definition lacks an exact scope binding"
            )
        if (
            definition_scope["kind"] != "universal"
            and definition_scope["selector"] != project_ref
        ):
            raise ProcessEntryRoutingError(
                "selected Process Definition is outside the confirmed project scope"
            )

    status = "ready"
    next_action = {
        "ordinary_generation": "submit_ordinary_generation",
        "capability_invocation": "begin_exact_definition_invocation",
        "capability_construction": "begin_management_interview",
        "capability_activation": "begin_activation_review",
    }[intent]
    if intent == "capability_construction" and not raw_confirmed:
        status = "awaiting_project_confirmation"
        next_action = "choose_project"
    elif (
        intent == "capability_invocation"
        and named_entry is not None
        and not bool(
            named_entry.get(
                "manual_invocation_available",
                named_entry.get("activated"),
            )
        )
    ):
        status = "awaiting_activation"
        next_action = "begin_activation_review"
    elif (intent in {"capability_invocation", "capability_activation"}
          and named_entry is None and resolved_framework_id is None):
        status = "awaiting_definition_selection"
        next_action = "choose_process_definition"

    definition_ref = (
        copy.deepcopy(named_entry["definition_ref"])
        if named_entry is not None and intent != "ordinary_generation" else None
    )
    contract: dict[str, Any] = {
        "schema_version": ENTRY_SCHEMA_VERSION,
        "source": source,
        "objective": objective,
        "project_ref": project_ref,
        "project_confirmed": raw_confirmed,
        "intent": intent,
        "classification_basis": basis,
        "status": status,
        "next_action": next_action,
        "definition_ref": definition_ref,
        "framework_id": resolved_framework_id,
        "authority_effects": [],
        "creates_process_run": False,
    }
    contract["contract_digest"] = _digest_json(contract)
    return contract


__all__ = [
    "ENTRY_INTENTS",
    "ENTRY_SCHEMA_VERSION",
    "ENTRY_SOURCES",
    "ENTRY_STATUSES",
    "ProcessEntryRoutingError",
    "list_entry_definitions",
    "load_programming_definition",
    "load_programming_entry",
    "route_process_entry",
]
