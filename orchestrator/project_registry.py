"""Project plugin registry — Ora's mechanism for projects to register
themselves and expose tools / slash commands / frameworks / PEDs /
workflow specs to the Ora runtime.

A project is any directory containing an ``ora-project.json`` manifest.
Projects register with Ora by writing a pointer file at
``~/ora/data/projects/<nexus>.json`` that points to the project root.
Ora discovers projects at startup by reading the pointer-file directory
(see ``list_projects``) and loads each project's manifest.

The convention is documented in
``Reference — Ora Project Plugin Convention.md`` (vault canonical).

This module is project-agnostic — nothing here references any specific
project. Project specifics (FRED fetch, MSI news indexer, etc.) live
in each project's own directory and are exposed through the manifest.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


POINTER_DIR = os.path.expanduser("~/ora/data/projects/")
MANIFEST_FILENAME = "ora-project.json"
DEFAULT_TOOL_TIMEOUT_SECS = 120

TOOL_INTERFACE_ARGV_STDOUT = "argv-stdout-json"
TOOL_INTERFACE_STDIN_STDOUT = "stdin-stdout-json"
KNOWN_INTERFACES = frozenset({TOOL_INTERFACE_ARGV_STDOUT, TOOL_INTERFACE_STDIN_STDOUT})

# Project nexus: lowercase kebab-case identifier (matches Ora's existing
# `project_nexus` convention used by PEDs and the oversight router).
_NEXUS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Capability slot name (Plugin Convention §12): lowercase letters, digits,
# underscores; matches the core slot-name convention in `capabilities.json`
# (e.g., `image_generates_cartoon`).
_SLOT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Allowed keys in a project `capability_slots[].routing` block.
# `preferred` and `fallback` are deliberately excluded — those are publisher
# decisions and live in `~/ora/config/routing-config.json::slots`, never in
# project manifests. See `Reference — Ora Project Plugin Convention.md` §12.
_PROJECT_ROUTING_KEYS = frozenset({
    "inherits", "prepend_fallback", "append_fallback",
    "exclude_inherited", "fallback_on",
})

# Mirrors `capability_registry._ACCEPTED_INPUT_TYPES` and
# `capabilities.json::_execution_patterns`. Kept here so the parser can
# validate at registration time without importing `capability_registry`
# (which would create a circular dependency at load time). Update when
# the registry's accepted sets change.
_KNOWN_INPUT_TYPES = frozenset({
    "text", "image-ref", "image-bytes", "mask", "direction-list",
    "count", "float", "enum", "images-list",
})
_KNOWN_EXECUTION_PATTERNS = frozenset({"sync", "async"})

# Theme id (Plugin Convention §13): same shape as the V3 server's
# `_v3_slugify` output. Lowercase, digits, hyphens, underscores; must
# start with a letter or digit. `default` is reserved for the
# Ora-shipped baseline and rejected at registration.
_THEME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_RESERVED_THEME_IDS = frozenset({"default"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProjectError(Exception):
    """Base class for project-registry errors."""


class ManifestError(ProjectError):
    """Manifest file is missing, malformed, or invalid."""


class ProjectNotFoundError(ProjectError):
    """No project registered with the given nexus."""


class ToolNotFoundError(ProjectError):
    """The requested tool or slash command is not declared in the manifest."""


class ToolInvocationError(ProjectError):
    """Tool subprocess failed (non-zero exit, timeout, malformed output, etc.)."""

    def __init__(self, message: str, *, exit_code: Optional[int] = None,
                 stderr: str = "", stdout: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr
        self.stdout = stdout


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class ProjectTool:
    """A tool exposed by a project. Invoked via subprocess; emits JSON on stdout.

    The tool's `command` array is the argv passed to subprocess. The second
    element (when present) is treated as a script path: if relative, it is
    resolved against the project root at invocation time. The first element
    (the interpreter) is left as-is — it's expected to be an executable on
    PATH (e.g., ``python3``) or an absolute path.
    """
    name: str
    command: list[str]
    description: str = ""
    interface: str = TOOL_INTERFACE_ARGV_STDOUT


@dataclass
class ProjectSlashCommand:
    """A chat-facing slash command exposed by a project.

    Same invocation contract as ProjectTool, but stdout is treated as
    free-form markdown rather than JSON. Used by the chat UI.
    """
    name: str  # without leading slash
    command: list[str]
    description: str = ""
    interface: str = TOOL_INTERFACE_ARGV_STDOUT


@dataclass
class ProjectCapabilitySlot:
    """A visual-capability slot declared by a project (Plugin Convention §12).

    ``contract`` carries the same shape as a ``capabilities.json::slots[name]``
    entry — ``required_inputs``, ``optional_inputs``, ``output``,
    ``execution_pattern``, ``common_errors``, ``summary``.

    ``routing`` declares structurally-project-specific directives only:
    ``inherits``, ``prepend_fallback``, ``append_fallback``,
    ``exclude_inherited``, ``fallback_on``. ``preferred`` and ``fallback``
    are publisher decisions and belong in ``~/ora/config/routing-config.json``;
    declaring them here raises a manifest error.
    """
    name: str
    contract: dict
    routing: dict = field(default_factory=dict)


@dataclass
class ProjectTheme:
    """A chat-UI theme declared by a project (Plugin Convention §13).

    The project ships theme assets (``theme.css`` + ``manifest.json``) at
    ``<project_root>/<directory>/``. The V3 server's ``_v3_read_index``
    layers project themes on top of the core themes index at server
    startup; ``/api/v3-themes/list`` surfaces them with the synthesized
    annotation ``origin = "project:<nexus>"``. Theme assets are served
    at request time from the project's directory via a dedicated route
    (``/themes/project/<nexus>/<filename>``) — no copy or symlink dance
    at startup; the project's directory is the source of truth.
    """
    id: str
    name: str
    directory: str


@dataclass
class Project:
    """A registered project — the in-memory representation of an ora-project.json."""
    nexus: str
    name: str
    root: Path
    version: str = "0.0.0"
    description: str = ""
    tools: dict[str, ProjectTool] = field(default_factory=dict)
    slash_commands: dict[str, ProjectSlashCommand] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    peds: list[str] = field(default_factory=list)
    workflow_specs: list[str] = field(default_factory=list)
    chromadb_collections: list[str] = field(default_factory=list)
    capability_slots: dict[str, ProjectCapabilitySlot] = field(default_factory=dict)
    themes: dict[str, ProjectTheme] = field(default_factory=dict)

    def resolve_path(self, relative: str) -> Path:
        """Resolve a path relative to the project root. Absolute paths pass through."""
        p = Path(relative).expanduser()
        if p.is_absolute():
            return p
        return (self.root / p).resolve()


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def _validate_nexus(nexus: Any, manifest_path: Path) -> str:
    if not isinstance(nexus, str) or not nexus:
        raise ManifestError(f"{manifest_path}: 'nexus' is required and must be a non-empty string")
    if not _NEXUS_RE.match(nexus):
        raise ManifestError(
            f"{manifest_path}: 'nexus' must be lowercase kebab-case "
            f"(letters/digits/hyphens/underscores, starting with a letter or digit); got {nexus!r}"
        )
    return nexus


def _validate_command(command: Any, context: str, manifest_path: Path) -> list[str]:
    if not isinstance(command, list) or not command:
        raise ManifestError(f"{manifest_path}: {context} 'command' must be a non-empty array")
    if not all(isinstance(c, str) and c for c in command):
        raise ManifestError(f"{manifest_path}: {context} 'command' entries must be non-empty strings")
    return list(command)


def _validate_interface(interface: Any, context: str, manifest_path: Path) -> str:
    if interface not in KNOWN_INTERFACES:
        raise ManifestError(
            f"{manifest_path}: {context} 'interface' must be one of "
            f"{sorted(KNOWN_INTERFACES)}; got {interface!r}"
        )
    return interface


def _parse_tools(raw: Any, manifest_path: Path) -> dict[str, ProjectTool]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ManifestError(f"{manifest_path}: 'tools' must be an array")
    tools: dict[str, ProjectTool] = {}
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            raise ManifestError(f"{manifest_path}: tools[{i}] must be an object")
        name = t.get("name")
        if not isinstance(name, str) or not name:
            raise ManifestError(f"{manifest_path}: tools[{i}] requires 'name' (non-empty string)")
        if name in tools:
            raise ManifestError(f"{manifest_path}: duplicate tool name {name!r}")
        command = _validate_command(t.get("command"), f"tools[{i}] ({name!r})", manifest_path)
        interface = _validate_interface(
            t.get("interface", TOOL_INTERFACE_ARGV_STDOUT),
            f"tools[{i}] ({name!r})", manifest_path,
        )
        tools[name] = ProjectTool(
            name=name,
            command=command,
            description=t.get("description", "") or "",
            interface=interface,
        )
    return tools


def _parse_slash_commands(raw: Any, manifest_path: Path) -> dict[str, ProjectSlashCommand]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ManifestError(f"{manifest_path}: 'slash_commands' must be an array")
    cmds: dict[str, ProjectSlashCommand] = {}
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ManifestError(f"{manifest_path}: slash_commands[{i}] must be an object")
        name = s.get("name")
        if not isinstance(name, str) or not name:
            raise ManifestError(f"{manifest_path}: slash_commands[{i}] requires 'name'")
        if name.startswith("/"):
            raise ManifestError(
                f"{manifest_path}: slash_commands[{i}] 'name' must NOT include the leading slash"
            )
        if name in cmds:
            raise ManifestError(f"{manifest_path}: duplicate slash_command name {name!r}")
        command = _validate_command(s.get("command"), f"slash_commands[{i}] ({name!r})", manifest_path)
        interface = _validate_interface(
            s.get("interface", TOOL_INTERFACE_ARGV_STDOUT),
            f"slash_commands[{i}] ({name!r})", manifest_path,
        )
        cmds[name] = ProjectSlashCommand(
            name=name,
            command=command,
            description=s.get("description", "") or "",
            interface=interface,
        )
    return cmds


def _parse_one_capability_slot(
    entry: Any, idx: int, manifest_path: Path,
) -> ProjectCapabilitySlot:
    """Validate one ``capability_slots`` entry against Plugin Convention §12.

    Raises ManifestError on any problem so the caller can skip just this
    entry without affecting the rest of the manifest.
    """
    ctx = f"capability_slots[{idx}]"
    if not isinstance(entry, dict):
        raise ManifestError(f"{ctx} must be an object")
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise ManifestError(f"{ctx} requires 'name' (non-empty string)")
    if not _SLOT_NAME_RE.match(name):
        raise ManifestError(
            f"{ctx} 'name' must match {_SLOT_NAME_RE.pattern} "
            f"(lowercase, underscore-separated); got {name!r}"
        )
    ctx = f"{ctx} ({name!r})"

    contract = entry.get("contract")
    if not isinstance(contract, dict):
        raise ManifestError(f"{ctx}: 'contract' is required and must be a JSON object")

    for input_field in ("required_inputs", "optional_inputs"):
        items = contract.get(input_field)
        if items is None:
            continue
        if not isinstance(items, list):
            raise ManifestError(f"{ctx}: contract.{input_field!r} must be an array")
        for j, item in enumerate(items):
            if not isinstance(item, dict):
                raise ManifestError(
                    f"{ctx}: contract.{input_field}[{j}] must be an object"
                )
            t = item.get("type")
            if t is not None and t not in _KNOWN_INPUT_TYPES:
                raise ManifestError(
                    f"{ctx}: contract.{input_field}[{j}].type {t!r} is not in "
                    f"the registry's accepted input types "
                    f"({sorted(_KNOWN_INPUT_TYPES)})"
                )

    pattern = contract.get("execution_pattern")
    if pattern is not None and pattern not in _KNOWN_EXECUTION_PATTERNS:
        raise ManifestError(
            f"{ctx}: contract.execution_pattern {pattern!r} not in "
            f"{sorted(_KNOWN_EXECUTION_PATTERNS)}"
        )

    routing = entry.get("routing", {}) or {}
    if not isinstance(routing, dict):
        raise ManifestError(f"{ctx}: 'routing' must be a JSON object")

    if "preferred" in routing or "fallback" in routing:
        raise ManifestError(
            f"{ctx}: 'preferred' and 'fallback' are publisher decisions and "
            f"belong in ~/ora/config/routing-config.json::slots, not in the "
            f"project manifest. Declare only structural directives: "
            f"{sorted(_PROJECT_ROUTING_KEYS)}"
        )

    extra = set(routing.keys()) - _PROJECT_ROUTING_KEYS
    if extra:
        raise ManifestError(
            f"{ctx}: unknown keys in routing block: {sorted(extra)}. "
            f"Allowed: {sorted(_PROJECT_ROUTING_KEYS)}"
        )

    return ProjectCapabilitySlot(name=name, contract=contract, routing=dict(routing))


def _parse_capability_slots(
    raw: Any, manifest_path: Path,
) -> dict[str, ProjectCapabilitySlot]:
    """Parse the ``capability_slots`` block (Plugin Convention §12).

    Top-level wrong type raises ManifestError (consistent with the other
    parsers). Individual malformed entries are skipped with a printed
    diagnostic, per §12's graceful-degradation rule ("a malformed
    capability_slots entry causes only that slot to be skipped").
    """
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ManifestError(f"{manifest_path}: 'capability_slots' must be an array")
    slots: dict[str, ProjectCapabilitySlot] = {}
    for i, entry in enumerate(raw):
        try:
            slot = _parse_one_capability_slot(entry, i, manifest_path)
        except ManifestError as e:
            print(f"[project_registry] Skipping capability_slot in {manifest_path}: {e}")
            continue
        if slot.name in slots:
            print(
                f"[project_registry] Skipping duplicate capability_slot "
                f"{slot.name!r} in {manifest_path}"
            )
            continue
        slots[slot.name] = slot
    return slots


def _parse_one_theme(
    entry: Any, idx: int, manifest_path: Path, project_root: Path,
) -> ProjectTheme:
    """Validate one ``themes`` entry against Plugin Convention §13.

    Raises ManifestError on any problem so the caller can skip just this
    entry without affecting the rest of the manifest. Asset-existence is
    checked here (the entry is only valid if its directory exists and
    contains both ``theme.css`` and ``manifest.json``).
    """
    ctx = f"themes[{idx}]"
    if not isinstance(entry, dict):
        raise ManifestError(f"{ctx} must be an object")
    tid = entry.get("id")
    if not isinstance(tid, str) or not tid:
        raise ManifestError(f"{ctx} requires 'id' (non-empty string)")
    if not _THEME_ID_RE.match(tid):
        raise ManifestError(
            f"{ctx} 'id' must match {_THEME_ID_RE.pattern}; got {tid!r}"
        )
    if tid in _RESERVED_THEME_IDS:
        raise ManifestError(
            f"{ctx} 'id' {tid!r} is reserved for the Ora-shipped baseline "
            f"and cannot be declared by a project"
        )
    ctx = f"{ctx} ({tid!r})"

    tname = entry.get("name")
    if not isinstance(tname, str) or not tname:
        raise ManifestError(f"{ctx}: 'name' is required and must be a non-empty string")

    directory = entry.get("directory")
    if not isinstance(directory, str) or not directory:
        raise ManifestError(f"{ctx}: 'directory' is required and must be a non-empty string")
    if Path(directory).is_absolute():
        raise ManifestError(
            f"{ctx}: 'directory' must be relative to the project root; got absolute path {directory!r}"
        )

    # Asset-existence check: the directory must exist and contain both
    # theme.css and manifest.json. Resolved against project_root.
    asset_dir = (project_root / directory).resolve()
    if not asset_dir.is_dir():
        raise ManifestError(
            f"{ctx}: 'directory' {directory!r} does not resolve to an existing directory "
            f"under the project root (looked at {asset_dir})"
        )
    for required in ("theme.css", "manifest.json"):
        if not (asset_dir / required).is_file():
            raise ManifestError(
                f"{ctx}: theme assets incomplete — missing {required} in {asset_dir}"
            )

    return ProjectTheme(id=tid, name=tname, directory=directory)


def _parse_themes(
    raw: Any, manifest_path: Path, project_root: Path,
) -> dict[str, ProjectTheme]:
    """Parse the ``themes`` block (Plugin Convention §13).

    Top-level wrong type raises ManifestError. Individual malformed
    entries are skipped with a printed diagnostic per §13's
    graceful-degradation rule.
    """
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ManifestError(f"{manifest_path}: 'themes' must be an array")
    themes: dict[str, ProjectTheme] = {}
    for i, entry in enumerate(raw):
        try:
            theme = _parse_one_theme(entry, i, manifest_path, project_root)
        except ManifestError as e:
            print(f"[project_registry] Skipping theme in {manifest_path}: {e}")
            continue
        if theme.id in themes:
            print(
                f"[project_registry] Skipping duplicate theme id "
                f"{theme.id!r} in {manifest_path}"
            )
            continue
        themes[theme.id] = theme
    return themes


def _parse_str_list(raw: Any, field_name: str, manifest_path: Path) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ManifestError(f"{manifest_path}: {field_name!r} must be an array of strings")
    if not all(isinstance(x, str) for x in raw):
        raise ManifestError(f"{manifest_path}: {field_name!r} entries must be strings")
    return list(raw)


def _parse_project_from_manifest(manifest_path: Path, root: Path) -> Project:
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ManifestError(f"Cannot read manifest {manifest_path}: {e}") from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ManifestError(f"{manifest_path}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError(f"{manifest_path}: top-level must be a JSON object")

    nexus = _validate_nexus(data.get("nexus"), manifest_path)
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ManifestError(f"{manifest_path}: 'name' is required and must be a non-empty string")

    return Project(
        nexus=nexus,
        name=name,
        root=root.resolve(),
        version=str(data.get("version", "0.0.0")),
        description=str(data.get("description", "") or ""),
        tools=_parse_tools(data.get("tools"), manifest_path),
        slash_commands=_parse_slash_commands(data.get("slash_commands"), manifest_path),
        frameworks=_parse_str_list(data.get("frameworks"), "frameworks", manifest_path),
        peds=_parse_str_list(data.get("peds"), "peds", manifest_path),
        workflow_specs=_parse_str_list(data.get("workflow_specs"), "workflow_specs", manifest_path),
        chromadb_collections=_parse_str_list(
            data.get("chromadb_collections"), "chromadb_collections", manifest_path,
        ),
        capability_slots=_parse_capability_slots(
            data.get("capability_slots"), manifest_path,
        ),
        themes=_parse_themes(data.get("themes"), manifest_path, root.resolve()),
    )


def load_project_at(root_path) -> Project:
    """Load a project from its root directory.

    Reads ``<root>/ora-project.json``, validates, returns Project.
    Raises ManifestError on missing or malformed manifest.
    """
    root = Path(os.path.expanduser(str(root_path)))
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ManifestError(f"No manifest at {manifest_path}")
    return _parse_project_from_manifest(manifest_path, root)


# ---------------------------------------------------------------------------
# Pointer-file management (~/ora/data/projects/<nexus>.json)
# ---------------------------------------------------------------------------


def _pointer_path(nexus: str, pointer_dir: str = POINTER_DIR) -> Path:
    return Path(os.path.expanduser(pointer_dir)) / f"{nexus}.json"


def list_projects(pointer_dir: str = POINTER_DIR) -> list[Project]:
    """Read all pointer files in pointer_dir and return loaded projects.

    Skips pointer files that point to missing or malformed manifests
    (with a diagnostic logged via print). Returns projects sorted by nexus.
    """
    pdir = Path(os.path.expanduser(pointer_dir))
    if not pdir.is_dir():
        return []
    projects: list[Project] = []
    for pf in sorted(pdir.glob("*.json")):
        try:
            pointer_data = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[project_registry] Skipping {pf}: invalid pointer file ({e})")
            continue
        if not isinstance(pointer_data, dict):
            print(f"[project_registry] Skipping {pf}: pointer must be a JSON object")
            continue
        root = pointer_data.get("root")
        if not root:
            print(f"[project_registry] Skipping {pf}: missing 'root'")
            continue
        try:
            project = load_project_at(root)
        except ManifestError as e:
            print(f"[project_registry] Skipping {pf}: {e}")
            continue
        if pointer_data.get("nexus") and pointer_data["nexus"] != project.nexus:
            print(
                f"[project_registry] Pointer/manifest nexus mismatch for {pf}: "
                f"pointer={pointer_data['nexus']!r}, manifest={project.nexus!r} (skipping)"
            )
            continue
        projects.append(project)
    return projects


def get_project(nexus: str, pointer_dir: str = POINTER_DIR) -> Optional[Project]:
    """Load a project by nexus, or None if not registered."""
    pf = _pointer_path(nexus, pointer_dir)
    if not pf.is_file():
        return None
    try:
        pointer_data = json.loads(pf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(pointer_data, dict):
        return None
    root = pointer_data.get("root")
    if not root:
        return None
    try:
        return load_project_at(root)
    except ManifestError:
        return None


def register_project(root_path, pointer_dir: str = POINTER_DIR) -> Project:
    """Register a project by writing a pointer file at <pointer_dir>/<nexus>.json.

    Validates the manifest before writing the pointer. Idempotent: re-registering
    the same nexus overwrites the existing pointer (use case: project root moved).

    Returns the loaded Project.
    """
    project = load_project_at(root_path)
    pdir = Path(os.path.expanduser(pointer_dir))
    pdir.mkdir(parents=True, exist_ok=True)
    pf = _pointer_path(project.nexus, pointer_dir)
    pf.write_text(
        json.dumps({"nexus": project.nexus, "root": str(project.root)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return project


def unregister_project(nexus: str, pointer_dir: str = POINTER_DIR) -> bool:
    """Delete the pointer file for a project. Returns True if a file was deleted."""
    pf = _pointer_path(nexus, pointer_dir)
    if pf.is_file():
        pf.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Tool invocation (the load-bearing API)
# ---------------------------------------------------------------------------


def _resolve_command(project: Project, command: list[str]) -> list[str]:
    """Resolve a tool/slash-command's argv: the second element (script path) is
    treated as project-relative when it isn't absolute. The first element
    (interpreter) and any additional args pass through unchanged.
    """
    if not command:
        raise ProjectError("Empty command")
    if len(command) < 2:
        return list(command)
    head, script, *rest = command
    script_path = Path(script).expanduser()
    if not script_path.is_absolute():
        script = str((project.root / script_path).resolve())
    return [head, script] + list(rest)


def _ora_home() -> str:
    """Return the Ora installation root (parent of the orchestrator directory).

    Project tools that depend on Ora's Python modules read this from the
    ORA_HOME env var that ``invoke_project_tool`` sets on every subprocess.
    """
    return str(Path(__file__).resolve().parent.parent)


def _build_subprocess_env(project: Project, extra_env: Optional[dict] = None) -> dict:
    """Build the subprocess environment with the standard Ora project env vars.

    Project tools can rely on these being set:
      - ORA_HOME           — path to the Ora installation root
      - ORA_VAULT          — path to the canonical vault (Ora-global)
      - ORA_PROJECT_NEXUS  — the nexus of the calling project
      - ORA_PROJECT_ROOT   — absolute path to the project root

    Optional env vars project tools MAY consume when set by the caller
    (install Chunk 3 — per-process configuration plumbing):
      - ORA_CONFIG_NAME    — named configuration from config/configurations/
                              the tool should invoke models with. When the
                              tool delegates to model_dispatch.invoke_chat,
                              it should pass config_name=os.environ.get(
                              "ORA_CONFIG_NAME") so the slot resolution
                              honors the configuration that drove the
                              invocation. Falls through to the Router's
                              context-derived default when unset.

    Extra env from the caller takes precedence over these defaults.
    """
    env = os.environ.copy()
    env.setdefault("ORA_HOME", _ora_home())
    env.setdefault("ORA_VAULT", os.path.expanduser("~/Documents/vault"))
    env["ORA_PROJECT_NEXUS"] = project.nexus
    env["ORA_PROJECT_ROOT"] = str(project.root)
    if extra_env:
        env.update(extra_env)
    return env


def invoke_project_tool(
    nexus: str,
    tool_name: str,
    args: Optional[list] = None,
    stdin_json: Any = None,
    timeout: int = DEFAULT_TOOL_TIMEOUT_SECS,
    pointer_dir: str = POINTER_DIR,
    extra_env: Optional[dict] = None,
) -> Any:
    """Invoke a project tool by name and return parsed JSON output.

    For ``argv-stdout-json`` tools, ``args`` are appended to the command's argv
    and ``stdin_json`` is ignored. For ``stdin-stdout-json`` tools, ``stdin_json``
    is serialized and piped to stdin and ``args`` is ignored. Both must produce
    valid JSON on stdout (or empty stdout, which returns ``None``).

    Raises:
        ProjectNotFoundError: no project registered with the given nexus.
        ToolNotFoundError: project has no tool with the given name.
        ToolInvocationError: subprocess failed (non-zero exit, timeout,
            executable not found, malformed JSON on stdout).
    """
    project = get_project(nexus, pointer_dir=pointer_dir)
    if project is None:
        raise ProjectNotFoundError(f"No project registered with nexus {nexus!r}")
    tool = project.tools.get(tool_name)
    if tool is None:
        raise ToolNotFoundError(
            f"Project {nexus!r} has no tool {tool_name!r}; "
            f"available: {sorted(project.tools.keys())}"
        )

    cmd = _resolve_command(project, tool.command)
    proc_input: Optional[bytes] = None
    if tool.interface == TOOL_INTERFACE_ARGV_STDOUT:
        if args:
            cmd = cmd + [str(a) for a in args]
    elif tool.interface == TOOL_INTERFACE_STDIN_STDOUT:
        proc_input = json.dumps(stdin_json or {}, ensure_ascii=False).encode("utf-8")
    else:
        raise ProjectError(f"Unknown interface {tool.interface!r}")

    env = _build_subprocess_env(project, extra_env=extra_env)

    try:
        result = subprocess.run(
            cmd,
            input=proc_input,
            capture_output=True,
            timeout=timeout,
            cwd=str(project.root),
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise ToolInvocationError(
            f"Tool {nexus}:{tool_name} timed out after {timeout}s",
            stderr=(e.stderr or b"").decode("utf-8", errors="replace"),
        ) from e
    except FileNotFoundError as e:
        raise ToolInvocationError(
            f"Tool {nexus}:{tool_name}: command executable not found ({e})"
        ) from e

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")

    if result.returncode != 0:
        raise ToolInvocationError(
            f"Tool {nexus}:{tool_name} exited with code {result.returncode}",
            exit_code=result.returncode, stderr=stderr, stdout=stdout,
        )

    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ToolInvocationError(
            f"Tool {nexus}:{tool_name} produced invalid JSON on stdout: {e}",
            exit_code=result.returncode, stderr=stderr, stdout=stdout,
        ) from e


def invoke_project_slash_command(
    nexus: str,
    command_name: str,
    args: Optional[list] = None,
    timeout: int = DEFAULT_TOOL_TIMEOUT_SECS,
    pointer_dir: str = POINTER_DIR,
) -> str:
    """Invoke a project slash command. Returns stdout as a markdown string.

    Unlike tools, slash commands return free-form text, not JSON, since
    their output goes directly to the chat UI. Errors are surfaced as a
    bracketed error string rather than raising — the chat UI always gets
    a renderable response.
    """
    project = get_project(nexus, pointer_dir=pointer_dir)
    if project is None:
        return f"[Slash command error: no project registered with nexus {nexus!r}]"
    sc = project.slash_commands.get(command_name)
    if sc is None:
        return (
            f"[Slash command error: project {nexus!r} has no slash command "
            f"{command_name!r}; available: {sorted(project.slash_commands.keys())}]"
        )

    cmd = _resolve_command(project, sc.command)
    if sc.interface == TOOL_INTERFACE_ARGV_STDOUT and args:
        cmd = cmd + [str(a) for a in args]

    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            cwd=str(project.root), env=_build_subprocess_env(project),
        )
    except subprocess.TimeoutExpired:
        return f"[Slash command {nexus}:{command_name} timed out after {timeout}s]"
    except FileNotFoundError as e:
        return f"[Slash command {nexus}:{command_name} executable not found: {e}]"

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        return (
            f"[Slash command {nexus}:{command_name} exited {result.returncode}]\n"
            + (f"```\n{stderr}\n```" if stderr.strip() else "")
        )
    return result.stdout.decode("utf-8", errors="replace")


def find_project_for_slash_command(
    name: str, pointer_dir: str = POINTER_DIR,
) -> Optional[Project]:
    """Find the (first) project that declares a slash command with the given name.

    Returns None if no project declares it. On collision, the project whose
    pointer file sorts first (alphabetically by nexus) wins; a diagnostic is
    logged. Project authors should namespace their command names to avoid
    collisions across projects that might be installed alongside one another.
    """
    matches = [p for p in list_projects(pointer_dir=pointer_dir) if name in p.slash_commands]
    if not matches:
        return None
    if len(matches) > 1:
        names = [p.nexus for p in matches]
        print(
            f"[project_registry] Slash command {name!r} declared by multiple projects "
            f"({names}); using {matches[0].nexus!r}"
        )
    return matches[0]


__all__ = [
    "POINTER_DIR",
    "MANIFEST_FILENAME",
    "TOOL_INTERFACE_ARGV_STDOUT",
    "TOOL_INTERFACE_STDIN_STDOUT",
    "ProjectError",
    "ManifestError",
    "ProjectNotFoundError",
    "ToolNotFoundError",
    "ToolInvocationError",
    "ProjectTool",
    "ProjectSlashCommand",
    "ProjectCapabilitySlot",
    "Project",
    "load_project_at",
    "list_projects",
    "get_project",
    "register_project",
    "unregister_project",
    "invoke_project_tool",
    "invoke_project_slash_command",
    "find_project_for_slash_command",
]
