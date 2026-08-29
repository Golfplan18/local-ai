"""Authoritative containment boundary for actionable Framework runs.

Every caller that can cause Framework work must pass through
``prepare_framework_execution`` before it selects a mode with a model, opens
scratch, writes a trace/event, or invokes an effect.  The returned object is
the only runtime representation of a model-executed Framework contract: all
references have already been resolved, or the call has failed closed.
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

try:
    from . import framework_parser as _parser
    from .framework_invocability import resolve_user_invocable_framework
except ImportError:  # direct orchestrator-module imports
    import framework_parser as _parser  # type: ignore
    from framework_invocability import resolve_user_invocable_framework  # type: ignore


class FrameworkPreflightError(ValueError):
    """The requested Framework is not safe to execute."""


# Legacy syntax is deliberately an identity allow-list, not a general parser
# fallback.  Removing a filename here is the state transition when that exact
# public Framework migrates to METHOD declarations.
LEGACY_LAYER_FRAMEWORKS = frozenset({
    "conversation-processing.md",
    "corpus-formalization.md",
    "deep-research-protocol.md",
    "knowledge-artifact-coach.md",
    "mindspec-interview.md",
    "mission-objectives-milestones.md",
    "output-formalization.md",
    "problem-evolution.md",
    "process-formalization.md",
    "process-inference.md",
    "terrain-mapping.md",
})


# Mechanical modes are recognized only as exact registered-framework/mode
# pairs.  A similarly named mode in another file is model-executed and must
# satisfy the strict contract.
MECHANICAL_REDIRECTS = {
    ("corpus-formalization.md", "C-Instance"):
        "/instance <template> <period> [<instance-dir>]",
    ("corpus-formalization.md", "C-Validate"):
        "/validate <instance> [<template>]",
    ("output-formalization.md", "O-Render"):
        "/render <off-spec> <instance> [<output-dir>]",
}

_METHOD_HEADING = re.compile(
    r"^### METHOD ([A-Za-z0-9][A-Za-z0-9_.-]*):\s*(\S.*?)\s*$"
)
_LEGACY_HEADING = re.compile(
    r"^## (?:LAYER|Layer) ([A-Za-z0-9][A-Za-z0-9_.-]*):\s*(\S.*?)\s*$"
)
_MODE_HEADING = re.compile(
    r"^### Milestones for Mode\s+(\S+)\s*$", re.MULTILINE,
)
_MILESTONE_H3 = re.compile(r"^### Milestone (\d+):\s*(\S.*?)\s*$")
_MILESTONE_H4 = re.compile(r"^#### Milestone (\d+):\s*(\S.*?)\s*$")
_PROPERTY = re.compile(
    r"^- \*\*([^:*]+):\*\*\s*(.*?)(?=\n- \*\*|\n\n|\Z)",
    re.MULTILINE | re.DOTALL,
)
_REFERENCE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_LEGACY_REFERENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PRIOR_ID = re.compile(r"^M[1-9][0-9]*$")
_GEAR4_PURPOSES = {
    "exploration",
    "independent corroboration",
    "both",
}
_PROFILE_UNSET = object()


@dataclass(frozen=True)
class ResolvedMethod:
    id: str
    name: str
    body: str
    legacy: bool = False


@dataclass(frozen=True)
class ResolvedMilestoneContract:
    mode: str
    milestone_id: str
    name: str
    endpoint_produced: str
    methods: tuple[ResolvedMethod, ...]
    required_prior: tuple[str, ...]
    external_prerequisites: tuple[tuple[str, Any], ...]
    verification_criterion: str
    gear: int
    gear4_purpose: Optional[str]
    output_format: str
    drift_check_question: str
    conditional_layers: Optional[str]
    declared_model_profile: Optional[str]
    model_profile_resolution: Mapping[str, Any]

    @property
    def id(self) -> str:
        """Compatibility name used by the milestone executor and trace code."""
        return self.milestone_id

    @property
    def layers_covered(self) -> tuple[str, ...]:
        """The executor consumes resolved methods, never parser layer labels."""
        return tuple(method.id for method in self.methods)

    @property
    def model_profile(self) -> Optional[str]:
        return self.declared_model_profile


@dataclass(frozen=True)
class PreparedM0Routing:
    function: str


@dataclass(frozen=True)
class PreparedFrameworkContract:
    """Recursively immutable execution view of one admitted Framework."""

    name: str
    file_path: str
    raw_markdown: str
    is_multi_mode: bool
    modes: tuple[str, ...]
    m0_routing: Optional[PreparedM0Routing]
    milestones_by_mode: Mapping[str, tuple[ResolvedMilestoneContract, ...]]

    def all_milestones(self) -> list[ResolvedMilestoneContract]:
        return [
            milestone
            for milestones in self.milestones_by_mode.values()
            for milestone in milestones
        ]


@dataclass(frozen=True)
class PreparedFramework:
    canonical_filename: str
    framework: PreparedFrameworkContract
    contract_text: str
    contracts: Mapping[tuple[str, str], ResolvedMilestoneContract]
    original_input: str
    exact_mode: Optional[str]
    effective_input: str
    mode_reasoning: Optional[str]
    mechanical_redirect: Optional[str]
    project_nexus: Optional[str]
    project_profile: Optional[str]
    one_run_profile: Optional[str]
    selector_profile_resolution: Mapping[str, Any]
    input_context: Mapping[str, Any]

    def contract_for(
        self, mode: str, milestone_id: str,
    ) -> ResolvedMilestoneContract:
        try:
            return self.contracts[(mode, milestone_id)]
        except KeyError as exc:
            raise FrameworkPreflightError(
                f"{self.canonical_filename}: no resolved contract for "
                f"{mode}.{milestone_id}"
            ) from exc


@dataclass(frozen=True)
class _MilestoneDeclaration:
    mode: str
    milestone_id: str
    name: str
    properties: Mapping[str, str]


def _freeze_value(value: Any) -> Any:
    """Recursively copy mutable caller/parser values into immutable values."""
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            frozen_key = _freeze_value(key)
            try:
                hash(frozen_key)
            except TypeError as exc:
                raise FrameworkPreflightError(
                    "Framework admission context has a mutable mapping key"
                ) from exc
            frozen[frozen_key] = _freeze_value(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    if value is None or isinstance(value, (str, bytes, bool, int, float, Path)):
        return copy.deepcopy(value)
    raise FrameworkPreflightError(
        "Framework admission values must be recursively immutable JSON-like values"
    )


def _thaw_value(value: Any) -> Any:
    """Return a caller-owned mutable copy of one admitted immutable value."""
    if isinstance(value, Mapping):
        return {copy.deepcopy(key): _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_value(item) for item in value}
    return copy.deepcopy(value)


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Capture one recursively immutable caller-owned context snapshot."""
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise FrameworkPreflightError(
            "Framework admission context must be a mapping"
        )
    return _freeze_value(value)


def prepared_input_context(
    prepared: PreparedFramework,
    additions: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a mutable execution copy while preserving admission authority.

    Later request assembly may add visual/runtime context, but it cannot
    replace values that were captured at Framework admission.  In particular,
    the resolved prerequisite and explicit-contributor lanes stay tied to the
    snapshot that made the run admissible.
    """
    merged = _thaw_value(additions or {})
    merged.update(_thaw_value(prepared.input_context))
    return merged


def _refusal(framework: str, detail: str) -> FrameworkPreflightError:
    return FrameworkPreflightError(
        f"Framework preflight refused {framework}: {detail}"
    )


def _consume_first_token(text: str) -> tuple[Optional[str], str]:
    """Consume one syntactic token and one delimiter, preserving the rest.

    ``split``/``join`` is forbidden on this boundary because it rewrites
    multiline prose, Markdown tables, and fenced code.  Leading whitespace is
    command syntax; after the token, exactly one separator character is
    consumed and every remaining character is returned unchanged.
    """
    match = re.match(r"\A\s*(\S+)", text or "")
    if match is None:
        return None, text or ""
    remainder = (text or "")[match.end():]
    if remainder and remainder[0].isspace():
        remainder = remainder[1:]
    return match.group(1), remainder


def _remove_config_flag(query: str) -> tuple[str, Optional[str]]:
    """Remove one ``--config VALUE`` span without normalizing other bytes."""
    matches = list(re.finditer(r"(?<!\S)--config(?=\s|\Z)", query))
    if len(matches) > 1:
        raise FrameworkPreflightError("--config may be supplied only once")
    if not matches:
        return query, None
    flag = matches[0]
    value_match = re.match(r"\s+(\S+)", query[flag.end():])
    if value_match is None:
        raise FrameworkPreflightError("--config requires a profile name")
    profile = value_match.group(1)
    start = flag.start()
    end = flag.end() + value_match.end()
    # Consume one separator belonging to the option so surrounding content
    # remains separated, but leave every other byte untouched.
    if start > 0 and query[start - 1].isspace():
        start -= 1
    elif end < len(query) and query[end].isspace():
        end += 1
    return query[:start] + query[end:], profile


def parse_framework_command_bytes(
    command: str,
) -> tuple[str, str, Optional[str]]:
    """Parse one typed Framework command while preserving its query bytes."""
    match = re.match(r"\A\s*/framework(?=\s|\Z)", command or "")
    if match is None:
        raise FrameworkPreflightError("not a /framework command")
    framework_ref, query = _consume_first_token((command or "")[match.end():])
    if framework_ref is None:
        raise FrameworkPreflightError("missing framework name")
    try:
        canonical = resolve_user_invocable_framework(framework_ref)
    except ValueError as exc:
        raise FrameworkPreflightError(str(exc)) from exc
    query, config_name = _remove_config_flag(query)
    return canonical, query, config_name


def is_framework_command_syntax(command: str) -> bool:
    """Recognize only the command token; the shared parser owns validity."""
    return bool(re.match(r"\A\s*/framework(?=\s|\Z)", command or ""))


def _mask_fences(text: str) -> tuple[str, tuple[str, ...]]:
    """Blank fenced content while retaining line positions.

    Declarations inside examples cannot become executable declarations.  The
    fenced lines are returned separately only so an unresolved reference can
    report that a same-named example was intentionally ignored.
    """
    masked: list[str] = []
    fenced: list[str] = []
    marker: Optional[str] = None
    marker_len = 0
    for raw_line in text.splitlines(keepends=True):
        stripped = raw_line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if marker is None and fence:
            token = fence.group(1)
            marker, marker_len = token[0], len(token)
            masked.append("\n" if raw_line.endswith("\n") else "")
            fenced.append(raw_line.rstrip("\n"))
            continue
        if marker is not None:
            fenced.append(raw_line.rstrip("\n"))
            if re.match(rf"\s*{re.escape(marker)}{{{marker_len},}}\s*$", raw_line):
                marker = None
                marker_len = 0
            masked.append("\n" if raw_line.endswith("\n") else "")
            continue
        masked.append(raw_line)
    if marker is not None:
        raise FrameworkPreflightError("unterminated fenced example")
    return "".join(masked), tuple(fenced)


def _heading_level(line: str) -> Optional[int]:
    match = re.match(r"^(#{1,6})\s+", line)
    return len(match.group(1)) if match else None


def _extract_declarations(
    text: str, canonical_filename: str,
) -> tuple[dict[str, ResolvedMethod], str]:
    lines = text.splitlines()
    candidates: list[tuple[int, int, re.Match[str], bool]] = []
    grammar: Optional[str] = None
    for index, line in enumerate(lines):
        method = _METHOD_HEADING.match(line)
        legacy = _LEGACY_HEADING.match(line)
        if line.startswith("### METHOD") and method is None:
            raise _refusal(canonical_filename, f"malformed METHOD heading on line {index + 1}")
        if re.match(r"^## (?:LAYER|Layer)(?:\s|$)", line) and legacy is None:
            raise _refusal(canonical_filename, f"malformed LAYER heading on line {index + 1}")
        if method:
            if grammar == "legacy":
                raise _refusal(canonical_filename, "METHOD and LAYER declaration grammar are mixed")
            grammar = "method"
            candidates.append((index, 3, method, False))
        elif legacy:
            if grammar == "method":
                raise _refusal(canonical_filename, "METHOD and LAYER declaration grammar are mixed")
            grammar = "legacy"
            candidates.append((index, 2, legacy, True))

    if grammar is None:
        raise _refusal(canonical_filename, "no executable METHOD declarations were found")
    if grammar == "legacy" and canonical_filename not in LEGACY_LAYER_FRAMEWORKS:
        raise _refusal(
            canonical_filename,
            "legacy LAYER declarations are not allowed for this registered identity",
        )

    declarations: dict[str, ResolvedMethod] = {}
    for start, level, match, legacy in candidates:
        reference_id, name = match.group(1), match.group(2).strip()
        if reference_id in declarations:
            raise _refusal(
                canonical_filename, f"duplicate declaration {reference_id!r}"
            )
        end = len(lines)
        for cursor in range(start + 1, len(lines)):
            next_level = _heading_level(lines[cursor])
            if next_level is not None and next_level <= level:
                end = cursor
                break
        body = "\n".join(lines[start + 1:end]).strip()
        if not body or _looks_placeholder(body):
            raise _refusal(
                canonical_filename,
                f"declaration {reference_id!r} has no usable instructions",
            )
        declarations[reference_id] = ResolvedMethod(
            id=reference_id, name=name, body=body, legacy=legacy,
        )
    return declarations, grammar


def _milestones_section(text: str, canonical_filename: str) -> str:
    matches = list(re.finditer(r"^## MILESTONES DELIVERED\s*$", text, re.MULTILINE))
    if len(matches) != 1:
        raise _refusal(
            canonical_filename,
            "expected exactly one operative MILESTONES DELIVERED section",
        )
    start = matches[0].end()
    next_h2 = re.search(r"^## (?!#)", text[start:], re.MULTILINE)
    return text[start:start + next_h2.start()] if next_h2 else text[start:]


def _parse_properties(
    body: str, canonical_filename: str, identity: str,
) -> dict[str, str]:
    properties: dict[str, str] = {}
    for match in _PROPERTY.finditer(body):
        key = match.group(1).strip().casefold()
        if key in properties:
            raise _refusal(
                canonical_filename,
                f"{identity} declares property {match.group(1).strip()!r} more than once",
            )
        properties[key] = match.group(2).strip()
    return properties


def _extract_milestones(
    text: str, canonical_filename: str,
) -> dict[tuple[str, str], _MilestoneDeclaration]:
    section = _milestones_section(text, canonical_filename)
    multi_mode = bool(_MODE_HEADING.search(section))
    lines = section.splitlines()
    current_mode = "all"
    modes_seen: dict[str, str] = {}
    mode_milestone_counts: dict[str, int] = {}
    headers: list[tuple[int, str, str, str, int]] = []
    for index, line in enumerate(lines):
        mode_match = _MODE_HEADING.match(line)
        if mode_match:
            current_mode = mode_match.group(1)
            folded_mode = current_mode.casefold()
            if folded_mode in modes_seen:
                raise _refusal(
                    canonical_filename,
                    f"duplicate mode identity {current_mode!r}; mode identities "
                    "must also be unique ignoring case",
                )
            modes_seen[folded_mode] = current_mode
            mode_milestone_counts[current_mode] = 0
            continue
        milestone = _MILESTONE_H4.match(line) if multi_mode else _MILESTONE_H3.match(line)
        malformed_prefix = "#### Milestone" if multi_mode else "### Milestone"
        if line.startswith(malformed_prefix) and milestone is None:
            raise _refusal(canonical_filename, f"malformed milestone heading on line {index + 1}")
        if milestone:
            if multi_mode and current_mode == "all":
                raise _refusal(
                    canonical_filename,
                    f"milestone {milestone.group(1)!r} appears before a mode declaration",
                )
            headers.append((
                index, current_mode, f"M{milestone.group(1)}",
                milestone.group(2).strip(), 4 if multi_mode else 3,
            ))
            mode_milestone_counts[current_mode] = (
                mode_milestone_counts.get(current_mode, 0) + 1
            )

    if multi_mode:
        empty_modes = [
            mode for mode in modes_seen.values()
            if mode_milestone_counts.get(mode, 0) == 0
        ]
        if empty_modes:
            raise _refusal(
                canonical_filename,
                f"declared mode(s) have no milestones: {', '.join(empty_modes)}",
            )

    declarations: dict[tuple[str, str], _MilestoneDeclaration] = {}
    for position, (start, mode, milestone_id, name, level) in enumerate(headers):
        end = len(lines)
        for cursor in range(start + 1, len(lines)):
            next_level = _heading_level(lines[cursor])
            if next_level is not None and next_level <= level:
                end = cursor
                break
        identity = f"{mode}.{milestone_id}"
        key = (mode, milestone_id)
        if key in declarations:
            raise _refusal(canonical_filename, f"duplicate milestone {identity}")
        body = "\n".join(lines[start + 1:end])
        declarations[key] = _MilestoneDeclaration(
            mode=mode,
            milestone_id=milestone_id,
            name=name,
            properties=_parse_properties(body, canonical_filename, identity),
        )
    if not declarations:
        raise _refusal(canonical_filename, "no operative milestones were found")
    return declarations


def _looks_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped.casefold() in {"none", "n/a", "tbd", "todo"}:
        return True
    return (
        (stripped.startswith("[") and stripped.endswith("]"))
        or (stripped.startswith("<") and stripped.endswith(">"))
    )


def _required_text(
    properties: Mapping[str, str], key: str, canonical_filename: str, identity: str,
) -> str:
    value = properties.get(key, "").strip()
    if _looks_placeholder(value):
        raise _refusal(canonical_filename, f"{identity} lacks a usable {key}")
    return value


def _split_references(
    raw: str, canonical_filename: str, identity: str, label: str,
    *, reference_pattern=_REFERENCE_ID,
) -> tuple[str, ...]:
    if raw.strip().casefold() == "none":
        return ()
    refs = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not refs or any(not reference_pattern.fullmatch(ref) for ref in refs):
        raise _refusal(
            canonical_filename,
            f"{identity} has an invalid {label}; use exact comma-separated identifiers or None",
        )
    if len(set(refs)) != len(refs):
        raise _refusal(canonical_filename, f"{identity} repeats a {label} reference")
    return refs


def _resolve_exact_mode(
    framework: Any,
    user_input: str,
    requested_mode: Optional[str],
    canonical_filename: str,
) -> tuple[Optional[str], str, Optional[str]]:
    if not framework.is_multi_mode:
        if requested_mode and requested_mode != "all":
            raise _refusal(canonical_filename, f"mode {requested_mode!r} is not declared")
        return "all", user_input, "single-mode framework"

    candidate = requested_mode
    remaining = user_input
    source = "requested mode"
    if candidate is None:
        candidate, remaining = _consume_first_token(user_input)
        if candidate is not None:
            source = "explicit first-token mode"
    if candidate is None:
        return None, user_input, None
    exact = next((mode for mode in framework.modes if mode.casefold() == candidate.casefold()), None)
    if exact is None:
        if requested_mode is not None:
            raise _refusal(canonical_filename, f"mode {requested_mode!r} is not declared")
        return None, user_input, None
    if requested_mode is not None:
        remaining = user_input
    return exact, remaining, f"{source}: exact registered mode {exact!r}"


def _lookup_process_profile(framework_name: str) -> Optional[str]:
    """Read the process-level Model Profile from the admitted routing bytes."""
    path = Path(__file__).resolve().parent.parent / "config" / "framework-routing.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FrameworkPreflightError(
            f"Model Profile routing is unreadable: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FrameworkPreflightError("Model Profile routing must be an object")
    mappings = payload.get("frameworks", {})
    if not isinstance(mappings, dict):
        raise FrameworkPreflightError("Model Profile framework routing must be an object")
    entry = mappings.get(framework_name)
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry.strip() or None
    if isinstance(entry, dict):
        value = entry.get("default_configuration")
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise FrameworkPreflightError(
                f"Model Profile routing for {framework_name!r} has an invalid default_configuration"
            )
        return value.strip()
    raise FrameworkPreflightError(
        f"Model Profile routing for {framework_name!r} has an invalid entry"
    )


def _resolve_effective_model_profile(
    *,
    project_nexus: Optional[str],
    process_profile: Optional[str],
    step_profile: Optional[str],
    one_run_profile: Optional[str],
) -> Mapping[str, Any]:
    """Resolve and freeze one complete five-level profile authority chain."""
    try:
        try:
            from . import model_profiles
        except ImportError:
            import model_profiles  # type: ignore
        resolution = model_profiles.resolve_effective_profile(
            project_nexus=project_nexus,
            process_profile=process_profile,
            step_profile=step_profile,
            one_run_profile=one_run_profile,
        )
    except Exception as exc:
        raise FrameworkPreflightError(
            f"Model Profile chain could not be resolved: {exc}"
        ) from exc
    if not isinstance(resolution, Mapping):
        raise FrameworkPreflightError("Model Profile resolution is not an object")
    selected = resolution.get("selected")
    runtime_name = selected.get("runtime_name") if isinstance(selected, Mapping) else None
    if not isinstance(runtime_name, str) or not runtime_name:
        raise FrameworkPreflightError(
            "Model Profile resolution has no exact runtime profile"
        )
    return _freeze_value(resolution)


def _prepared_framework_contract(
    parsed: _parser.Framework,
    raw_markdown: str,
    contracts: Mapping[tuple[str, str], ResolvedMilestoneContract],
) -> PreparedFrameworkContract:
    """Discard the mutable parser graph and retain admitted value objects only."""
    by_mode = {
        mode: tuple(
            contracts[(mode, milestone.id)]
            for milestone in milestones
            if (mode, milestone.id) in contracts
        )
        for mode, milestones in parsed.milestones_by_mode.items()
    }
    return PreparedFrameworkContract(
        name=str(parsed.name),
        file_path=str(parsed.file_path),
        raw_markdown=str(raw_markdown),
        is_multi_mode=bool(parsed.is_multi_mode),
        modes=tuple(str(mode) for mode in parsed.modes),
        m0_routing=(
            PreparedM0Routing(function=str(parsed.m0_routing.function))
            if parsed.m0_routing is not None else None
        ),
        milestones_by_mode=MappingProxyType(by_mode),
    )


def _load_bound_text(
    canonical_filename: str, project_nexus: Optional[str],
) -> tuple[str, str, Optional[str]]:
    path = os.path.join(_parser.FRAMEWORKS_DIR, canonical_filename)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise _refusal(canonical_filename, f"registered specification is unreadable: {exc}") from exc

    try:
        try:
            from .project_registry import get_project
            from .framework_config import compose_framework_spec
        except ImportError:
            from project_registry import get_project  # type: ignore
            from framework_config import compose_framework_spec  # type: ignore
        framework_id = canonical_filename[:-3]
        if not isinstance(project_nexus, str) or not project_nexus.strip():
            return compose_framework_spec(
                framework_id, spec_text=raw,
            ), path, None

        nexus = project_nexus.strip()
        project = get_project(nexus)
        if project is None:
            raise _refusal(canonical_filename, f"project {nexus!r} is not registered")
        profiles = [
            item.profile_name for item in project.framework_configurations
            if item.framework == framework_id
        ]
        if not profiles:
            return compose_framework_spec(
                framework_id, spec_text=raw,
            ), path, None
        if len(profiles) != 1:
            raise _refusal(
                canonical_filename,
                f"project {nexus!r} declares {len(profiles)} configuration profiles; exact binding is ambiguous",
            )
        return compose_framework_spec(
            framework_id,
            project_nexus=nexus,
            profile_name=profiles[0],
            spec_text=raw,
            project=project,
        ), path, profiles[0]
    except FrameworkPreflightError:
        raise
    except Exception as exc:
        raise _refusal(
            canonical_filename,
            f"project configuration could not be resolved: {exc}",
        ) from exc


def prepare_framework_execution(
    framework_ref: str,
    user_input: str = "",
    *,
    requested_mode: Optional[str] = None,
    project_nexus: Optional[str] = None,
    one_run_profile: Optional[str] = None,
    input_context: Optional[Mapping[str, Any]] = None,
) -> PreparedFramework:
    """Resolve an actionable Framework completely, or refuse it.

    ``framework_ref`` is resolved through the public registry even when the
    caller already holds a filename.  This prevents a direct executor caller
    from smuggling an arbitrary Markdown path across the boundary.
    """
    try:
        canonical_filename = resolve_user_invocable_framework(framework_ref)
    except ValueError as exc:
        raise FrameworkPreflightError(f"Framework preflight refused: {exc}") from exc

    normalized_project = (
        project_nexus.strip()
        if isinstance(project_nexus, str) and project_nexus.strip()
        else None
    )
    if one_run_profile is not None and (
        not isinstance(one_run_profile, str) or not one_run_profile.strip()
    ):
        raise _refusal(canonical_filename, "one-run Model Profile is invalid")
    normalized_one_run_profile = (
        one_run_profile.strip() if isinstance(one_run_profile, str) else None
    )
    captured_input_context = _frozen_mapping(input_context)
    raw, path, project_profile = _load_bound_text(
        canonical_filename, normalized_project,
    )
    try:
        executable_text, fenced_lines = _mask_fences(raw)
    except FrameworkPreflightError as exc:
        raise _refusal(canonical_filename, str(exc)) from exc
    try:
        framework = _parser.parse_framework_text(executable_text, path=path)
    except Exception as exc:
        raise _refusal(canonical_filename, f"contract parsing failed: {exc}") from exc

    exact_mode, effective_input, mode_reasoning = _resolve_exact_mode(
        framework, user_input, requested_mode, canonical_filename,
    )
    mechanical_redirect = MECHANICAL_REDIRECTS.get(
        (canonical_filename, exact_mode or "")
    )
    milestone_declarations = _extract_milestones(executable_text, canonical_filename)

    if mechanical_redirect is not None:
        selected = [
            declaration for (mode, _), declaration in milestone_declarations.items()
            if mode == exact_mode
        ]
        if len(selected) != 1:
            raise _refusal(
                canonical_filename,
                f"mechanical mode {exact_mode!r} must declare exactly one milestone",
            )
        properties = selected[0].properties
        gear = properties.get("gear", "").strip()
        if gear != "1":
            raise _refusal(canonical_filename, f"mechanical mode {exact_mode!r} must declare exact Gear 1")
        _required_text(properties, "verification criterion", canonical_filename, f"{exact_mode}.{selected[0].milestone_id}")
        _required_text(properties, "output format", canonical_filename, f"{exact_mode}.{selected[0].milestone_id}")
        immutable_framework = _prepared_framework_contract(framework, raw, {})
        return PreparedFramework(
            canonical_filename=canonical_filename,
            framework=immutable_framework,
            contract_text=raw,
            contracts=MappingProxyType({}),
            original_input=user_input,
            exact_mode=exact_mode,
            effective_input=effective_input,
            mode_reasoning=mode_reasoning,
            mechanical_redirect=mechanical_redirect,
            project_nexus=normalized_project,
            project_profile=project_profile,
            one_run_profile=normalized_one_run_profile,
            selector_profile_resolution=MappingProxyType({}),
            input_context=captured_input_context,
        )

    declarations, grammar = _extract_declarations(executable_text, canonical_filename)
    fenced_ids = {
        match.group(1)
        for line in fenced_lines
        for match in [_METHOD_HEADING.match(line) or _LEGACY_HEADING.match(line)]
        if match is not None
    }
    framework_milestones = {
        (mode, milestone.id): milestone
        for mode, milestones in framework.milestones_by_mode.items()
        for milestone in milestones
    }
    if set(framework_milestones) != set(milestone_declarations):
        raise _refusal(canonical_filename, "parsed milestone identities do not match the operative declarations")

    prerequisite_values = (
        captured_input_context.get("framework_prerequisites", {})
        if isinstance(captured_input_context, Mapping) else {}
    )
    if not isinstance(prerequisite_values, Mapping):
        raise _refusal(canonical_filename, "framework_prerequisites must be a mapping")

    contracts: dict[tuple[str, str], ResolvedMilestoneContract] = {}
    referenced_declarations: set[str] = set()
    positions = {
        (mode, milestone.id): index
        for mode, milestones in framework.milestones_by_mode.items()
        for index, milestone in enumerate(milestones)
    }
    process_profile = _lookup_process_profile(framework.name)
    selector_profile_resolution = _resolve_effective_model_profile(
        project_nexus=normalized_project,
        process_profile=process_profile,
        step_profile=None,
        one_run_profile=normalized_one_run_profile,
    )
    for identity, raw_declaration in milestone_declarations.items():
        mode, milestone_id = identity
        if (canonical_filename, mode) in MECHANICAL_REDIRECTS:
            continue
        properties = raw_declaration.properties
        reference_property = "methods" if grammar == "method" else "layers covered"
        method_ids = _split_references(
            _required_text(properties, reference_property, canonical_filename, f"{mode}.{milestone_id}"),
            canonical_filename,
            f"{mode}.{milestone_id}",
            reference_property,
            reference_pattern=(
                _LEGACY_REFERENCE_ID if grammar == "legacy" else _REFERENCE_ID
            ),
        )
        resolved_methods: list[ResolvedMethod] = []
        for method_id in method_ids:
            method = declarations.get(method_id)
            if method is None:
                qualifier = " (a fenced example with that id was ignored)" if method_id in fenced_ids else ""
                raise _refusal(
                    canonical_filename,
                    f"{mode}.{milestone_id} references unresolved {reference_property[:-1]} {method_id!r}{qualifier}",
                )
            resolved_methods.append(method)
            referenced_declarations.add(method_id)

        prior_raw = properties.get("required prior milestones", "").strip()
        if not prior_raw:
            raise _refusal(canonical_filename, f"{mode}.{milestone_id} lacks required prior milestones")
        priors = _split_references(
            prior_raw, canonical_filename, f"{mode}.{milestone_id}", "same-run prior",
        )
        for prior in priors:
            if not _PRIOR_ID.fullmatch(prior):
                raise _refusal(canonical_filename, f"{mode}.{milestone_id} has non-same-run prior {prior!r}")
            prior_key = (mode, prior)
            if prior_key not in positions or positions[prior_key] >= positions[identity]:
                raise _refusal(canonical_filename, f"{mode}.{milestone_id} has unresolved earlier prior {prior!r}")

        external_raw = properties.get("external prerequisites", "").strip()
        if not external_raw:
            raise _refusal(canonical_filename, f"{mode}.{milestone_id} lacks external prerequisites")
        external_ids = _split_references(
            external_raw, canonical_filename, f"{mode}.{milestone_id}", "external prerequisite",
        )
        resolved_external: list[tuple[str, Any]] = []
        for prerequisite_id in external_ids:
            if prerequisite_id not in prerequisite_values or prerequisite_values[prerequisite_id] is None:
                raise _refusal(
                    canonical_filename,
                    f"{mode}.{milestone_id} has unresolved external prerequisite {prerequisite_id!r}",
                )
            resolved_external.append((prerequisite_id, prerequisite_values[prerequisite_id]))

        verification = _required_text(
            properties, "verification criterion", canonical_filename, f"{mode}.{milestone_id}",
        )
        output_format = _required_text(
            properties, "output format", canonical_filename, f"{mode}.{milestone_id}",
        )
        gear_raw = properties.get("gear", "").strip()
        if not re.fullmatch(r"[2-4]", gear_raw):
            raise _refusal(
                canonical_filename,
                f"{mode}.{milestone_id} lacks an exact model-executed Gear "
                "value from 2 through 4",
            )
        gear = int(gear_raw)
        purpose_raw = properties.get("gear 4 purpose", "").strip()
        purpose = re.sub(r"\s+", " ", purpose_raw.casefold()) or None
        if gear == 4:
            if purpose not in _GEAR4_PURPOSES:
                raise _refusal(
                    canonical_filename,
                    f"{mode}.{milestone_id} lacks an exact Gear 4 purpose (exploration, independent corroboration, or both)",
                )
        elif purpose is not None:
            raise _refusal(canonical_filename, f"{mode}.{milestone_id} declares an unused Gear 4 purpose")

        parsed_milestone = framework_milestones[identity]
        if parsed_milestone.gear != gear:
            raise _refusal(canonical_filename, f"{mode}.{milestone_id} Gear did not parse exactly")
        declared_model_profile = properties.get("model profile", "").strip() or None
        profile_resolution = _resolve_effective_model_profile(
            project_nexus=normalized_project,
            process_profile=process_profile,
            step_profile=declared_model_profile,
            one_run_profile=normalized_one_run_profile,
        )
        contracts[identity] = ResolvedMilestoneContract(
            mode=mode,
            milestone_id=milestone_id,
            name=raw_declaration.name,
            endpoint_produced=properties.get("endpoint produced", "").strip(),
            methods=tuple(resolved_methods),
            required_prior=tuple(priors),
            external_prerequisites=tuple(
                (key, _freeze_value(value)) for key, value in resolved_external
            ),
            verification_criterion=verification,
            gear=gear,
            gear4_purpose=purpose,
            output_format=output_format,
            drift_check_question=properties.get("drift check question", "").strip(),
            conditional_layers=properties.get("conditional layers", "").strip() or None,
            declared_model_profile=declared_model_profile,
            model_profile_resolution=profile_resolution,
        )

    unused = sorted(set(declarations) - referenced_declarations)
    if unused:
        raise _refusal(canonical_filename, f"unused declaration(s): {', '.join(unused)}")
    if not contracts:
        raise _refusal(canonical_filename, "no model-executed milestone contract was resolved")

    immutable_framework = _prepared_framework_contract(framework, raw, contracts)
    return PreparedFramework(
        canonical_filename=canonical_filename,
        framework=immutable_framework,
        contract_text=raw,
        contracts=MappingProxyType(dict(contracts)),
        original_input=user_input,
        exact_mode=exact_mode,
        effective_input=effective_input,
        mode_reasoning=mode_reasoning,
        mechanical_redirect=None,
        project_nexus=normalized_project,
        project_profile=project_profile,
        one_run_profile=normalized_one_run_profile,
        selector_profile_resolution=selector_profile_resolution,
        input_context=captured_input_context,
    )


def reuse_prepared_framework(
    prepared: PreparedFramework,
    framework_ref: str,
    user_input: str,
    *,
    requested_mode: Optional[str] = None,
    project_nexus: Optional[str] = None,
    one_run_profile: Any = _PROFILE_UNSET,
    input_context: Optional[Mapping[str, Any]] = None,
) -> PreparedFramework:
    """Rebind request-local input to an admitted contract without rereading it."""
    if not isinstance(prepared, PreparedFramework):
        raise FrameworkPreflightError("Framework admission snapshot is invalid")
    try:
        canonical = resolve_user_invocable_framework(framework_ref)
    except ValueError as exc:
        raise FrameworkPreflightError(f"Framework preflight refused: {exc}") from exc
    if canonical != prepared.canonical_filename:
        raise _refusal(
            canonical,
            "the supplied admission snapshot belongs to a different Framework",
        )
    normalized_project = (
        project_nexus.strip()
        if isinstance(project_nexus, str) and project_nexus.strip()
        else None
    )
    if normalized_project != prepared.project_nexus:
        raise _refusal(
            canonical,
            "the project binding changed after Framework admission",
        )
    if one_run_profile is not _PROFILE_UNSET:
        normalized_profile = (
            one_run_profile.strip()
            if isinstance(one_run_profile, str) and one_run_profile.strip()
            else None
        )
        if normalized_profile != prepared.one_run_profile:
            raise _refusal(
                canonical,
                "the one-run Model Profile changed after Framework admission",
            )
    exact_mode, effective_input, mode_reasoning = _resolve_exact_mode(
        prepared.framework,
        user_input,
        requested_mode,
        canonical,
    )
    if (
        prepared.exact_mode is not None
        and exact_mode is not None
        and exact_mode != prepared.exact_mode
    ):
        raise _refusal(canonical, "the exact mode changed after Framework admission")
    mechanical_redirect = MECHANICAL_REDIRECTS.get((canonical, exact_mode or ""))
    merged_context = prepared_input_context(prepared, input_context)
    return replace(
        prepared,
        original_input=user_input,
        exact_mode=exact_mode,
        effective_input=effective_input,
        mode_reasoning=mode_reasoning,
        mechanical_redirect=mechanical_redirect,
        input_context=_frozen_mapping(merged_context),
    )


def preflight_framework_command(
    command: str,
    *,
    project_nexus: Optional[str] = None,
    one_run_profile: Optional[str] = None,
    input_context: Optional[Mapping[str, Any]] = None,
) -> PreparedFramework:
    """Preflight a typed ``/framework`` command without invoking its executor."""
    canonical, query, command_profile = parse_framework_command_bytes(command)
    if (
        command_profile is not None
        and one_run_profile is not None
        and command_profile != one_run_profile
    ):
        raise FrameworkPreflightError(
            "the command and input toolbar specify different one-run Model Profiles"
        )
    return prepare_framework_execution(
        canonical,
        query,
        project_nexus=project_nexus,
        one_run_profile=command_profile or one_run_profile,
        input_context=input_context,
    )
