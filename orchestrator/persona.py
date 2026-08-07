"""File-backed Persona loading, resolution, and MindSpec compilation."""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path

import yaml

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


PERSONAS_DIR = Path(_rp.ORA_HOME) / "personas"
REQUIRED_SECTIONS = (
    "Relationship Baseline",
    "Principles and Guardrails",
    "Perspective",
    "Audience Contracts",
    "Relationship Matrix",
)
PERSONA_BLOCK_PREFIX = "[PERSONA — "
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^## +(.+?)[ \t]*$", re.MULTILINE)


class PersonaError(ValueError):
    """A Persona cannot be used without changing its meaning."""


def _split_sections(body: str) -> dict[str, str]:
    matches = list(_HEADING_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1).strip()] = body[start:end]
    return sections


def _validate_style(style: object) -> dict:
    if not isinstance(style, dict):
        raise PersonaError("frontmatter style must be an object")
    try:
        from style_assembly import AXIS_ORDER, RUNGS, load_arrangement_schemas
    except ImportError:  # pragma: no cover
        from orchestrator.style_assembly import AXIS_ORDER, RUNGS, load_arrangement_schemas
    arrangement = style.get("arrangement")
    if arrangement not in load_arrangement_schemas():
        raise PersonaError(f"unknown style arrangement: {arrangement!r}")
    if style.get("register_default") not in ("written", "conversational"):
        raise PersonaError("style register_default must be written or conversational")
    demeanor = style.get("demeanor")
    if not isinstance(demeanor, dict):
        raise PersonaError("style demeanor must be an object")
    for axis in AXIS_ORDER:
        if demeanor.get(axis) not in RUNGS[axis]:
            raise PersonaError(f"invalid style demeanor {axis}: {demeanor.get(axis)!r}")
    conversational = style.get("conversational", {})
    if not isinstance(conversational, dict):
        raise PersonaError("style conversational must be an object")
    conversational_demeanor = conversational.get("demeanor", {})
    if not isinstance(conversational_demeanor, dict):
        raise PersonaError("style conversational demeanor must be an object")
    if not isinstance(conversational.get("devices", {}), dict):
        raise PersonaError("style conversational devices must be an object")
    for axis, rung in conversational_demeanor.items():
        if axis not in RUNGS or rung not in RUNGS[axis]:
            raise PersonaError(f"invalid conversational demeanor {axis}: {rung!r}")
    for key in ("devices", "glossary", "format"):
        if not isinstance(style.get(key, {}), dict):
            raise PersonaError(f"style {key} must be an object")
    glossary = style.get("glossary") or {}
    if not isinstance(glossary.get("canonical", {}), dict):
        raise PersonaError("style glossary canonical must be an object")
    for key in ("required", "forbidden"):
        if not isinstance(glossary.get(key, []), list):
            raise PersonaError(f"style glossary {key} must be a list")
    try:
        elaboration = int(style.get("elaboration", 3))
    except (TypeError, ValueError) as exc:
        raise PersonaError("style elaboration must be 1-5") from exc
    if not 1 <= elaboration <= 5:
        raise PersonaError("style elaboration must be 1-5")
    return dict(style)


def parse_persona(text: str, identifier: str, path: str | None = None) -> dict:
    if not _ID_RE.fullmatch(identifier or ""):
        raise PersonaError(f"invalid Persona identifier: {identifier!r}")
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        raise PersonaError("Persona requires YAML frontmatter")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise PersonaError(f"invalid Persona frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise PersonaError("Persona frontmatter must be an object")
    display_name = metadata.get("display_name")
    description = metadata.get("description")
    if not isinstance(display_name, str) or not display_name.strip():
        raise PersonaError("Persona display_name is required")
    if not isinstance(description, str) or not description.strip():
        raise PersonaError("Persona description is required")
    body = text[match.end():]
    headings = tuple(item.strip() for item in _HEADING_RE.findall(body))
    if headings != REQUIRED_SECTIONS:
        raise PersonaError(
            "Persona sections must appear exactly once in the required order"
        )
    sections = _split_sections(body)
    missing = [
        name for name in REQUIRED_SECTIONS
        if not sections.get(name, "").strip()
    ]
    if missing:
        raise PersonaError("Persona missing section(s): " + ", ".join(missing))
    return {
        "id": identifier,
        "display_name": display_name.strip(),
        "description": description.strip(),
        "provenance": metadata.get("provenance") or {},
        "style": _validate_style(metadata.get("style")),
        "sections": {name: sections[name].strip() for name in REQUIRED_SECTIONS},
        "principles_raw": sections["Principles and Guardrails"],
        "path": path,
    }


def load_persona(identifier: str, personas_dir: str | Path | None = None) -> dict:
    if not _ID_RE.fullmatch(identifier or ""):
        raise PersonaError(f"invalid Persona identifier: {identifier!r}")
    base = Path(personas_dir or PERSONAS_DIR)
    path = base / f"{identifier}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaError(f"Persona {identifier!r} is unavailable") from exc
    return parse_persona(text, identifier, str(path))


def list_personas(personas_dir: str | Path | None = None) -> dict:
    base = Path(personas_dir or PERSONAS_DIR)
    choices, errors = [], []
    if base.is_dir():
        for path in sorted(base.glob("*.md")):
            try:
                item = load_persona(path.stem, base)
                choices.append({
                    "id": item["id"],
                    "display_name": item["display_name"],
                    "description": item["description"],
                })
            except PersonaError as exc:
                errors.append({"id": path.stem, "error": str(exc)})
    return {"personas": choices, "errors": errors}


def _project_persona_id(project_nexus: str | None) -> str | None:
    try:
        try:
            from active_project import get_active_project
            from project_meta import read_project_meta
        except ImportError:  # pragma: no cover
            from orchestrator.active_project import get_active_project
            from orchestrator.project_meta import read_project_meta
        nexus = project_nexus if project_nexus is not None else get_active_project()
        if not isinstance(nexus, str) or nexus.lower() in ("", "commons", "general"):
            return None
        value = (read_project_meta(nexus) or {}).get("persona")
        return value.strip() if isinstance(value, str) and value.strip() else None
    except Exception:
        return None


def _global_persona_id(global_id: str | None) -> str:
    if global_id is not None:
        return global_id.strip() if isinstance(global_id, str) else ""
    try:
        try:
            import user_settings
        except ImportError:  # pragma: no cover
            from orchestrator import user_settings
        value = user_settings.get_setting("styles.persona_id", "ora")
        return value.strip() if isinstance(value, str) and value.strip() else "ora"
    except Exception:
        return "ora"


def _runtime_block(persona: dict, warnings: list[str]) -> str:
    lines = [f"{PERSONA_BLOCK_PREFIX}{persona['display_name']}]",
             "Assistant behavior only. Subordinate to the Ora constitution, current task, and binding framework/process contracts.",
             f"When acting as the user's personal assistant, identify yourself as {persona['display_name']}, disclose your assistant role, and never impersonate the user."]
    if warnings:
        lines.append("Selection notice: " + " ".join(warnings))
    for heading in REQUIRED_SECTIONS:
        lines.extend(("", f"## {heading}", "", persona["sections"][heading]))
    return "\n".join(lines).strip()


def resolve_persona(
    project_nexus: str | None = None,
    global_id: str | None = None,
    project_persona_id: str | None = None,
    personas_dir: str | Path | None = None,
) -> dict:
    """Resolve one Persona: project, then global, then packaged Ora."""
    warnings: list[str] = []
    requested_project = (
        project_persona_id if project_persona_id is not None
        else _project_persona_id(project_nexus)
    )
    candidates = []
    if isinstance(requested_project, str) and requested_project.strip():
        candidates.append(("project", requested_project.strip()))
    requested_global = _global_persona_id(global_id)
    if requested_global:
        candidates.append(("global", requested_global))
    seen = set()
    for source, identifier in candidates:
        if identifier in seen:
            continue
        seen.add(identifier)
        try:
            persona = load_persona(identifier, personas_dir)
            return {
                **persona, "source": source, "warnings": warnings,
                "runtime_markdown": _runtime_block(persona, warnings),
                "style_entry": persona["style"],
            }
        except PersonaError as exc:
            warnings.append(f"Requested {source} Persona {identifier!r} was not usable: {exc}.")
    try:
        persona = load_persona("ora", personas_dir)
    except PersonaError as exc:
        warnings.append(f"Packaged Ora Persona was not usable: {exc}.")
        raise PersonaError(" ".join(warnings)) from exc
    warnings.append("Using the packaged Ora Persona.")
    return {
        **persona, "source": "built-in", "warnings": warnings,
        "runtime_markdown": _runtime_block(persona, warnings),
        "style_entry": persona["style"],
    }


_ADAPTATION_OPTIONS = {
    "warmth": ("cool", "even", "warm"),
    "directness": ("diplomatic", "plain", "blunt"),
    "pacing": ("unhurried", "steady", "brisk"),
    "challenge": ("gentle", "balanced", "firm"),
    "framing": ("reflective", "balanced", "action-oriented"),
    "communication": ("question-led", "adaptive", "recommendation-led"),
}
_ADAPTATION_KEYS = (*_ADAPTATION_OPTIONS, "explanation_density")

COMPILER_SYSTEM_PROMPT = """\
Choose bounded assistant-behavior adaptations from the MindSpec portrait.
Return exactly one JSON object with every key shown in this example:
{"warmth":"even","directness":"plain","pacing":"steady",
"challenge":"balanced","explanation_density":3,"framing":"balanced",
"communication":"adaptive"}
Allowed values: warmth cool/even/warm; directness diplomatic/plain/blunt;
pacing unhurried/steady/brisk; challenge gentle/balanced/firm; explanation_density
integer 1–5; framing reflective/balanced/action-oriented; communication
question-led/adaptive/recommendation-led. Return no Markdown, prose, names,
biography, interview content, assessment terms, extra keys, or commentary.
"""


def _invoke_default(system_prompt: str, user_prompt: str, slot: str) -> str:
    try:
        from model_dispatch import invoke_chat
    except ImportError:  # pragma: no cover
        from orchestrator.model_dispatch import invoke_chat
    return invoke_chat(system_prompt, user_prompt, slot=slot)


def _parse_adaptations(raw: str) -> dict:
    def _strict_object(pairs):
        parsed = dict(pairs)
        if len(parsed) != len(pairs):
            raise PersonaError("compiler output must not contain duplicate keys")
        return parsed

    try:
        selected = json.loads(raw or "", object_pairs_hook=_strict_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PersonaError("compiler output must be one JSON object") from exc
    if not isinstance(selected, dict) or set(selected) != set(_ADAPTATION_KEYS):
        raise PersonaError("compiler output must contain exactly the allowed adaptation keys")
    for key, options in _ADAPTATION_OPTIONS.items():
        if selected[key] not in options:
            raise PersonaError(f"compiler output has an invalid {key} selection")
    density = selected["explanation_density"]
    if isinstance(density, bool) or not isinstance(density, int) or not 1 <= density <= 5:
        raise PersonaError("compiler output has an invalid explanation_density selection")
    return selected


def _render_compiled_persona(base: dict, selected: dict) -> str:
    warmth = {
        "cool": "restrained in warmth", "even": "even in warmth",
        "warm": "openly warm",
    }[selected["warmth"]]
    directness = {
        "diplomatic": "diplomatic", "plain": "plain-spoken", "blunt": "blunt",
    }[selected["directness"]]
    pacing = {
        "unhurried": "unhurried", "steady": "steady-paced", "brisk": "brisk",
    }[selected["pacing"]]
    challenge = {
        "gentle": "challenge gently after establishing understanding",
        "balanced": "challenge candidly when it materially helps",
        "firm": "surface consequential contradictions promptly and press for resolution",
    }[selected["challenge"]]
    density = {
        1: "minimal explanation", 2: "concise explanation",
        3: "balanced explanation", 4: "example-rich explanation",
        5: "exhaustive explanation",
    }[selected["explanation_density"]]
    framing = {
        "reflective": "begin with meaning and context before action",
        "balanced": "balance reflection, evidence, and action",
        "action-oriented": "begin with the decision or next action, then supply context",
    }[selected["framing"]]
    communication = {
        "question-led": "lead with one useful question before proposing a direction",
        "adaptive": "mix concise reflection, questions, and recommendations as the task requires",
        "recommendation-led": "state a recommendation first, then invite correction",
    }[selected["communication"]]

    style = copy.deepcopy(base["style"])
    challenge_style = {
        "gentle": ("gentle", "accommodating"),
        "balanced": ("measured", "candid"),
        "firm": ("forceful", "challenging"),
    }[selected["challenge"]]
    pace_energy = {"unhurried": "calm", "steady": "steady", "brisk": "lively"}
    arrangement = {
        "reflective": "scene-reflection",
        "balanced": "answer-first",
        "action-oriented": "goal-steps",
    }
    for demeanor in (
        style.setdefault("demeanor", {}),
        style.setdefault("conversational", {}).setdefault("demeanor", {}),
    ):
        demeanor.update({
            "warmth": selected["warmth"],
            "directness": selected["directness"],
            "energy": pace_energy[selected["pacing"]],
            "force": challenge_style[0],
            "agreeableness": challenge_style[1],
        })
    style["elaboration"] = selected["explanation_density"]
    style["arrangement"] = arrangement[selected["framing"]]

    sections = copy.deepcopy(base["sections"])
    sections["Relationship Baseline"] += (
        f"\n\nAdaptation: Be {warmth}, {directness}, and {pacing}; {challenge}."
    )
    sections["Perspective"] += (
        f"\n\nAdaptation: Use {density}; {framing}; {communication}."
    )
    sections["Audience Contracts"] += (
        f"\n\nAdaptation: Keep both audiences {directness} and {pacing}. "
        f"Use {density}; {communication}; {framing}."
    )
    sections["Relationship Matrix"] += (
        f"\n\nAdapted demeanor and pacing: Processing and Consolation stay {warmth} "
        f"and {pacing}; Advisory is {directness} and should {challenge}; "
        f"Companionship is {warmth} and {pacing}."
    )

    compiled_metadata = {
        "display_name": base["display_name"],
        "description": base["description"],
        "provenance": copy.deepcopy(base.get("provenance") or {}),
        "style": style,
    }
    frontmatter = "---\n" + yaml.safe_dump(
        compiled_metadata, sort_keys=False,
    ).rstrip() + "\n---"
    parts = [frontmatter, "\n\n", f"# {base['display_name']}", "\n\n"]
    for index, heading in enumerate(REQUIRED_SECTIONS):
        parts.append(f"## {heading}")
        if heading == "Principles and Guardrails":
            parts.append(base["principles_raw"])
        else:
            parts.extend(("\n\n", sections[heading]))
            parts.append("\n\n" if index < len(REQUIRED_SECTIONS) - 1 else "\n")
    return "".join(parts)


def compile_self_spec(
    spec_text: str,
    base_id: str | None = None,
    output_id: str | None = None,
    invoke=None,
    slot: str = "breadth",
    personas_dir: str | Path | None = None,
) -> dict:
    """Create one validated inactive Persona, refusing silent overwrite."""
    if not isinstance(spec_text, str) or not spec_text.strip():
        return {"ok": False, "error": "self-spec is empty"}
    base_resolution = resolve_persona(
        global_id=base_id or None,
        project_persona_id="",
        personas_dir=personas_dir,
    )
    base = base_resolution
    identifier = output_id or f"{base['id']}-personalized"
    if not _ID_RE.fullmatch(identifier):
        return {"ok": False, "error": f"invalid output Persona identifier: {identifier!r}"}
    output_path = Path(personas_dir or PERSONAS_DIR) / f"{identifier}.md"
    if output_path.exists():
        return {"ok": False, "error": f"Persona {identifier!r} already exists; no file was overwritten"}
    invoke = invoke or _invoke_default
    user_prompt = (
        "BASE PERSONA (behavior and style to tailor; preserve its constitutional floor):\n\n"
        + base["runtime_markdown"]
        + "\n\nBASE STYLE:\n"
        + yaml.safe_dump(base["style"], sort_keys=False)
        + "\n\nMINDSPEC PORTRAIT (source material; do not reproduce):\n\n"
        + spec_text.strip()
    )
    try:
        raw = invoke(COMPILER_SYSTEM_PROMPT, user_prompt, slot)
        selected = _parse_adaptations(raw or "")
        candidate = _render_compiled_persona(base, selected)
        validated = parse_persona(candidate, identifier, str(output_path))
        if validated["principles_raw"] != base["principles_raw"]:
            raise PersonaError("protected principles changed")
        if validated["provenance"] != base.get("provenance", {}):
            raise PersonaError("base provenance changed")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{identifier}.", suffix=".tmp", dir=output_path.parent,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(candidate)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, output_path)
            except FileExistsError as exc:
                raise PersonaError(
                    f"Persona {identifier!r} already exists; no file was overwritten"
                ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "id": identifier,
        "path": str(output_path),
        "display_name": validated["display_name"],
        "active": False,
    }


__all__ = [
    "PERSONAS_DIR", "PERSONA_BLOCK_PREFIX", "PersonaError",
    "REQUIRED_SECTIONS", "compile_self_spec", "list_personas", "load_persona",
    "parse_persona", "resolve_persona",
]
