"""Framework configuration runtime (Plugin Convention §14, chunk 2).

When a framework spec runs, project-supplied configuration values get
substituted into ``${config.<key>}`` references inside the spec body
before the composed text is handed to prompt assembly. This module is
the runtime side of §14's "configuration profile binding" mechanism.

Public API
----------

``compose_framework_spec(framework_name, project_nexus=None,
                          profile_name=None) -> str``
    Load the spec from ``frameworks/book/<framework_name>.md``, find the
    invoking project's profile (when ``project_nexus`` is given), then
    substitute ``${config.<key>}`` references in the spec body. Returns
    the composed spec text. With no project context, falls back to the
    spec's declared defaults; if a reference has neither a project value
    nor a declared default, raises :class:`FrameworkConfigError` so
    misalignment surfaces loudly.

``parse_config_interface(spec_text) -> dict``
    Read the spec's ``## CONFIGURATION INTERFACE`` section and return
    the declared configuration keys with their defaults. Returns ``{}``
    when the spec has no configuration interface section. Used by
    :func:`compose_framework_spec` to resolve defaults; exposed for
    testing + tooling that wants to introspect declared interfaces.

``substitute_config_refs(spec_text, supplied_config, declared_defaults)
                          -> str``
    Pure substitution helper. Replaces every ``${config.<key>}`` in
    ``spec_text`` with a value from ``supplied_config`` (priority 1) or
    ``declared_defaults`` (priority 2). Raises :class:`FrameworkConfigError`
    on unresolved references. Exposed for unit testing; production
    callers should use :func:`compose_framework_spec`.

Errors are raised as :class:`FrameworkConfigError` with a ``code``
field for programmatic dispatch (``unresolved_reference``,
``framework_not_found``, ``project_not_registered``,
``profile_not_declared``).

This module deliberately does NOT touch the existing ``load_framework``
in ``boot.py``. Callers that want project binding opt in by calling
``compose_framework_spec`` instead. Chunk 4 (the migration of
``document-processing.md``) switches that one framework's call sites
over; everything else continues to use ``load_framework`` and runs
project-neutral as before.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

# The workspace root comes from the one path layer that resolves it
# (ORA_HOME first, ~/ora otherwise), so a clone installed anywhere finds
# its own frameworks — and so framework_parser, which loads the same
# directory, provably agrees with this module rather than approximately.
try:
    from . import runtime_paths as _rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as _rp  # type: ignore

_WORKSPACE = _rp.WORKSPACE
FRAMEWORKS_DIR = Path(_WORKSPACE) / "frameworks" / "book"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FrameworkConfigError(Exception):
    """Raised by the framework-config runtime on unresolved substitution,
    missing framework, missing project, or missing profile.

    ``code`` is one of:
      * ``framework_not_found`` — ``frameworks/book/<name>.md`` missing
      * ``project_not_registered`` — supplied ``project_nexus`` not in
        the project registry
      * ``profile_not_declared`` — the project doesn't declare a
        ``framework_configurations`` entry matching the supplied
        ``(framework, profile_name)`` pair
      * ``unresolved_reference`` — a ``${config.<key>}`` reference in
        the spec body has neither a supplied value nor a declared default
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


# ---------------------------------------------------------------------------
# Configuration-interface parser
# ---------------------------------------------------------------------------

# Matches the start of the `## CONFIGURATION INTERFACE` section. Trailing
# content (until the next `##` heading or EOF) is the section body.
_CFG_IFACE_SECTION_RE = re.compile(
    r"^##\s+CONFIGURATION INTERFACE\b\s*\n(.*?)(?=\n##\s|\Z)",
    re.DOTALL | re.MULTILINE,
)

# Matches a top-level bullet declaring a configuration key:
#
#     - **`chromadb_collection`** (string, default: `knowledge`) — ...
#
# Capture groups: 1 = key name, 2 = full parenthetical (or empty),
# 3 = default value string (or empty when no default declared).
_CFG_KEY_BULLET_RE = re.compile(
    r"^-\s+\*\*`(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)`\*\*"
    r"(?:\s*\((?P<paren>[^)]*)\))?"
    r"(?:\s*[—\-]\s*.*)?$",
    re.MULTILINE,
)

# Inside the parenthetical, find a `default: <value>` clause. Value can be:
# - a backtick-quoted literal: `null`, `knowledge`, `"some string"`, `5`, `0.1`
# - or the bare word null (no backticks)
_DEFAULT_CLAUSE_RE = re.compile(
    r"default:\s*(?:`(?P<backtick>[^`]*)`|(?P<bare>null|None))",
    re.IGNORECASE,
)


def _decode_default_literal(literal: str) -> object:
    """Turn a default-clause literal into a Python value.

    Heuristics (simplest-first):
      - "null" / "None" → None
      - "true" / "false" → bool
      - integer-looking → int
      - float-looking → float
      - everything else → string (with surrounding quotes stripped)
    """
    if literal is None:
        return None
    s = literal.strip()
    if s.lower() in ("null", "none"):
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s[:1] in ("[", "{"):
        try:
            return json.loads(s)
        except ValueError:
            pass
    # Numeric?
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    # Strip outer quotes if present
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _parse_config_declarations(spec_text: str) -> dict[str, tuple[str, object]]:
    """Return exact declared types and defaults, rejecting duplicate keys."""
    match = _CFG_IFACE_SECTION_RE.search(spec_text)
    if not match:
        return {}
    declarations: dict[str, tuple[str, object]] = {}
    for bullet_match in _CFG_KEY_BULLET_RE.finditer(match.group(1)):
        key = bullet_match.group("key")
        if key in declarations:
            raise FrameworkConfigError(
                "duplicate_config_key",
                f"Configuration interface declares {key!r} more than once.",
            )
        paren = (bullet_match.group("paren") or "").strip()
        default_match = _DEFAULT_CLAUSE_RE.search(paren)
        if default_match:
            literal = default_match.group("backtick")
            if literal is None:
                literal = default_match.group("bare")
            default = _decode_default_literal(literal)
            declared_type = re.split(
                r",\s*default\s*:", paren, maxsplit=1, flags=re.IGNORECASE,
            )[0].strip()
        else:
            default = NO_DEFAULT
            declared_type = paren
        declarations[key] = (declared_type, default)
    return declarations


def parse_config_interface(spec_text: str) -> dict:
    """Return ``{key: default}`` for every key declared in the spec's
    ``## CONFIGURATION INTERFACE`` section.

    Keys without a declared default have value ``_NO_DEFAULT`` — the
    sentinel callers check to distinguish "no default supplied" from
    "default is None". Use :data:`NO_DEFAULT` to test.

    Returns ``{}`` when the spec has no configuration interface
    section — framework runs project-neutral with no substitutions
    expected.
    """
    return {
        key: default
        for key, (_declared_type, default) in _parse_config_declarations(
            spec_text
        ).items()
    }


# Sentinel returned by parse_config_interface when a key has no
# declared default. Distinguishable from None (which is a valid
# declared default value).
class _NoDefault:
    def __repr__(self):
        return "<NO_DEFAULT>"


NO_DEFAULT = _NoDefault()


def _value_matches_declared_type(value: object, declared_type: str) -> bool:
    normalized = re.sub(r"\s+", " ", declared_type.replace("`", "")).strip().casefold()
    nullable = normalized.endswith(" or null")
    if nullable:
        if value is None:
            return True
        normalized = normalized[:-8].strip()
    if normalized == "string":
        return isinstance(value, str)
    if normalized == "list of strings":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if normalized in {"integer", "int"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized in {"number", "float"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if normalized in {"boolean", "bool"}:
        return isinstance(value, bool)
    object_match = re.fullmatch(r"object(?:\s*\{([^}]*)\})?", normalized)
    if object_match:
        if not isinstance(value, dict):
            return False
        fields = object_match.group(1)
        if fields is None:
            return True
        expected = {field.strip() for field in fields.split(",") if field.strip()}
        return set(value) == expected
    return False


def _validate_config_values(spec_text: str, supplied: dict) -> dict:
    declarations = _parse_config_declarations(spec_text)
    undeclared = sorted(set(supplied) - set(declarations))
    if undeclared:
        raise FrameworkConfigError(
            "undeclared_config_key",
            f"Project configuration supplies undeclared key(s): {', '.join(undeclared)}.",
        )
    for key, value in supplied.items():
        declared_type = declarations[key][0]
        if not declared_type or not _value_matches_declared_type(value, declared_type):
            raise FrameworkConfigError(
                "config_type_mismatch",
                f"Configuration value {key!r} does not match declared type "
                f"{declared_type or '(missing)'!r}.",
            )
    for key, (declared_type, default) in declarations.items():
        if default is NO_DEFAULT or key in supplied:
            continue
        if not declared_type or not _value_matches_declared_type(default, declared_type):
            raise FrameworkConfigError(
                "config_type_mismatch",
                f"Default value for {key!r} does not match declared type "
                f"{declared_type or '(missing)'!r}.",
            )
    return {key: default for key, (_kind, default) in declarations.items()}


# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------

_CONFIG_REF_RE = re.compile(r"\$\{config\.([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Matches `<!-- ora-project-extension: <id> -->` markers anywhere in
# the spec body. Whitespace tolerant; id matches the same regex used
# in the manifest parser. Captured: 1 = extension-point id.
_EXTENSION_POINT_MARKER_RE = re.compile(
    r"<!--\s*ora-project-extension:\s*([a-z][a-z0-9_-]*)\s*-->"
)


def substitute_config_refs(
    spec_text: str,
    supplied_config: dict,
    declared_defaults: dict,
) -> str:
    """Replace every ``${config.<key>}`` in ``spec_text`` with a value
    from ``supplied_config`` (priority 1) or ``declared_defaults``
    (priority 2). Raises :class:`FrameworkConfigError(unresolved_reference)`
    on any reference that has neither.

    Substitution renders the value via ``str()``. A ``None`` value
    renders as the string ``"null"`` (matches JSON null semantics for
    the framework spec, which is a markdown document).
    """
    unresolved: list = []

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in supplied_config:
            value = supplied_config[key]
        elif key in declared_defaults and declared_defaults[key] is not NO_DEFAULT:
            value = declared_defaults[key]
        else:
            unresolved.append(key)
            return match.group(0)  # leave as-is for the error message
        if value is None:
            return "null"
        return str(value)

    result = _CONFIG_REF_RE.sub(_replace, spec_text)
    if unresolved:
        deduped = sorted(set(unresolved))
        raise FrameworkConfigError(
            "unresolved_reference",
            f"Framework spec references {deduped} via ${{config.*}} but the "
            f"value is neither supplied by the project's profile nor declared "
            f"with a default in the spec's '## CONFIGURATION INTERFACE' "
            f"section. Either supply the value in the project's "
            f"framework_configurations[].config block, or add a default to "
            f"the framework's CONFIGURATION INTERFACE."
        )
    return result


# ---------------------------------------------------------------------------
# Extension-point overlays (chunk 3)
# ---------------------------------------------------------------------------

def splice_extension_overlays(
    spec_text: str,
    overlays_by_extension_point: dict,
) -> str:
    """Replace each ``<!-- ora-project-extension: <id> -->`` marker in
    ``spec_text`` with the matching overlay text (when supplied), or
    drop the marker (when no overlay is supplied for that id).

    ``overlays_by_extension_point`` maps extension-point id → overlay
    text. Every supplied id must have exactly one matching marker in the
    spec so composition cannot silently drop or ambiguously place contract
    material.

    Marker semantics:
      * Marker present + overlay supplied → marker replaced by overlay
        text, surrounded by blank lines so the splice reads cleanly in
        markdown
      * Marker present + no overlay supplied → marker removed (becomes
        empty string); the surrounding markdown reads the same as if
        the marker had never been there
      * Overlay supplied + no matching marker in spec → rejected

    This pass is idempotent: re-running it on already-spliced text is
    a no-op because the markers are gone.
    """
    marker_ids = _EXTENSION_POINT_MARKER_RE.findall(spec_text)
    duplicate_markers = sorted({
        marker_id for marker_id in marker_ids if marker_ids.count(marker_id) > 1
    })
    if duplicate_markers:
        raise FrameworkConfigError(
            "duplicate_extension_marker",
            "Framework spec repeats extension marker(s): "
            + ", ".join(duplicate_markers),
        )
    unmatched = sorted(set(overlays_by_extension_point) - set(marker_ids))
    if unmatched:
        raise FrameworkConfigError(
            "unmatched_overlay",
            "Project overlay(s) have no matching Framework marker: "
            + ", ".join(unmatched),
        )

    def _replace(match: re.Match) -> str:
        ep_id = match.group(1)
        overlay = overlays_by_extension_point.get(ep_id)
        if overlay is None:
            return ""  # marker removed; no overlay supplied for this point
        # Surround with blank lines so the spliced text reads as a
        # standalone block rather than running into the surrounding prose.
        return f"\n\n{overlay.rstrip()}\n\n"

    return _EXTENSION_POINT_MARKER_RE.sub(_replace, spec_text)


def _load_overlay_files(
    project,
    framework_name: str,
    profile_name: str,
) -> dict:
    """Read every overlay file declared by the project's profile and
    return ``{extension_point_id: overlay_text}``.

    A declared overlay is part of the exact composed contract.  If it
    disappears or becomes unreadable after registration, composition refuses;
    silently dropping it would execute a different contract.
    """
    bare = framework_name[:-3] if framework_name.endswith(".md") else framework_name
    fc_entry = project.find_framework_configuration(bare, profile_name)
    if fc_entry is None:
        return {}
    out: dict = {}
    try:
        root = Path(project.root).resolve(strict=True)
    except (AttributeError, OSError) as exc:
        raise FrameworkConfigError(
            "overlay_unreadable",
            f"Project root is unavailable while loading overlays: {exc}",
        ) from exc
    for overlay in fc_entry.overlays:
        if overlay.extension_point in out:
            raise FrameworkConfigError(
                "duplicate_overlay",
                "Project profile repeats overlay extension point "
                f"{overlay.extension_point!r}.",
            )
        try:
            path = (root / overlay.file).resolve(strict=True)
        except OSError as exc:
            raise FrameworkConfigError(
                "overlay_unreadable",
                f"Cannot resolve declared overlay {overlay.file!r}: {exc}",
            ) from exc
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise FrameworkConfigError(
                "overlay_path_escape",
                f"Declared overlay {overlay.file!r} resolves outside project root {root}.",
            ) from exc
        try:
            out[overlay.extension_point] = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FrameworkConfigError(
                "overlay_unreadable",
                f"Cannot read declared overlay for extension point "
                f"{overlay.extension_point!r} at {path}: {exc}",
            ) from exc
    return out


# ---------------------------------------------------------------------------
# Top-level composition
# ---------------------------------------------------------------------------

def _load_spec_file(framework_name: str) -> str:
    """Read the framework spec from frameworks/book/<name>.md.

    Accepts either a bare framework id ("document-processing") or a
    filename ("document-processing.md"). Raises
    :class:`FrameworkConfigError(framework_not_found)` when missing.
    """
    name = framework_name
    if not name.endswith(".md"):
        name = name + ".md"
    path = FRAMEWORKS_DIR / name
    if not path.is_file():
        raise FrameworkConfigError(
            "framework_not_found",
            f"Framework spec not found: {path}",
        )
    return path.read_text(encoding="utf-8")


def compose_framework_spec(
    framework_name: str,
    project_nexus: Optional[str] = None,
    profile_name: Optional[str] = None,
    spec_text: Optional[str] = None,
    project=None,
) -> str:
    """Load + bind a framework spec for runtime invocation.

    Without project context (no ``project_nexus`` supplied, or supplied
    but the project doesn't declare a profile), the framework runs
    project-neutral: ``${config.<key>}`` references are substituted with
    declared defaults from the spec's ``## CONFIGURATION INTERFACE``
    section. References without defaults raise
    :class:`FrameworkConfigError(unresolved_reference)`.

    With project context, the project's
    ``framework_configurations[(framework_name, profile_name)].config``
    block supplies values; references not in the project's block fall
    back to declared defaults.

    After config substitution, this function also splices project-
    supplied extension-point overlays at their ``<!-- ora-project-
    extension: <id> -->`` markers in the spec body. Unsupplied markers
    are dropped; supplied overlays without exactly one matching marker
    are rejected. With no project context, all markers are dropped (the
    spec reads project-neutral), but duplicate markers are still rejected.

    ``spec_text`` lets a caller that already holds the spec body — the
    milestone executor, which is handed an explicit ``framework_path``
    rather than a bare id — supply it directly. Without it the body is
    read from ``frameworks/book/<framework_name>.md``, which is only
    the same file when the framework lives in the book directory.
    """
    if spec_text is None:
        spec_text = _load_spec_file(framework_name)
    declared = parse_config_interface(spec_text)

    supplied: dict = {}
    overlays: dict = {}
    if project_nexus is not None:
        # Defensive import — keep this module independent of
        # project_registry at load time so import cycles don't bite.
        try:
            from orchestrator.project_registry import get_project
        except Exception as exc:
            raise FrameworkConfigError(
                "project_not_registered",
                f"Cannot import project_registry ({exc}); "
                f"framework spec cannot be project-bound.",
            ) from exc
        bound_project = project if project is not None else get_project(project_nexus)
        if bound_project is None:
            raise FrameworkConfigError(
                "project_not_registered",
                f"No project registered with nexus {project_nexus!r}.",
            )
        if bound_project.nexus != project_nexus:
            raise FrameworkConfigError(
                "project_not_registered",
                f"Captured project {bound_project.nexus!r} does not match "
                f"requested nexus {project_nexus!r}.",
            )
        if profile_name is not None:
            # Use the bare framework id for lookup (strip .md if caller
            # supplied a filename).
            bare = framework_name[:-3] if framework_name.endswith(".md") else framework_name
            fc = bound_project.find_framework_configuration(bare, profile_name)
            if fc is None:
                raise FrameworkConfigError(
                    "profile_not_declared",
                    f"Project {project_nexus!r} does not declare a "
                    f"framework_configurations entry for "
                    f"({bare!r}, {profile_name!r}).",
                )
            supplied = dict(fc.config)
            overlays = _load_overlay_files(
                bound_project, framework_name, profile_name,
            )

    declared = _validate_config_values(spec_text, supplied)
    substituted = substitute_config_refs(spec_text, supplied, declared)
    return splice_extension_overlays(substituted, overlays)


__all__ = [
    "FrameworkConfigError",
    "NO_DEFAULT",
    "FRAMEWORKS_DIR",
    "parse_config_interface",
    "substitute_config_refs",
    "splice_extension_overlays",
    "compose_framework_spec",
]
