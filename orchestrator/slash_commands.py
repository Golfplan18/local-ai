"""Slash-command dispatcher — wires chat slash commands to runtime calls.

Exposes the meta-layer's mechanical runtime operations through the chat
interface. Each command bypasses the analytical pipeline (no model call,
no Phase A.5, no gear pipeline) and produces a single markdown response.

Recognized commands:

  /instance <template> <period> [<instance-dir>]
      Create a corpus instance from a template for the given period.
      Default instance-dir: ~/Documents/vault/Corpus Instances/

  /validate <instance> [<template>]
      Validate a populated corpus instance against its template.
      Template is auto-resolved from the instance frontmatter when omitted.

  /render <off-spec> <instance> [<output-dir>]
      Render a corpus instance through a bespoke OFF spec.
      Default output-dir: the vault root.

  /queue
      List pending entries in the human-review queue.

  /approve <index> [<proposed-definition>]
      Approve a pending redefinition. Use /queue to find the index.

  /deny <index> [<reason>]
      Deny a pending redefinition. Use /queue to find the index.

  /cleaning [detect|resolve|status] [options]
      Engram Cleaning Framework — cross-vault contradiction sweep.
      `/cleaning` (no args) → status summary
      `/cleaning detect [strategy] [limit]` → produce triage queue
      `/cleaning resolve [--apply]` → apply queued resolutions (dry-run by default)
      `/cleaning status` → queue state without re-running detection

Path resolution for input files: absolute path is tried first, then
relative-to-cwd, relative-to-vault, relative-to-ora. The first hit wins.

Per Reference — Meta-Layer Architecture; the deferred runtime-invocation
slash commands listed in the 2026-05-04 implementation handoff §"Genuinely
Deferred (Next Session)" item 1.
"""
from __future__ import annotations

import os
import re
import shlex
from typing import Optional

# Repo root (…/ora), derived from THIS file's location so the historical-tool
# import fallbacks below resolve wherever Ora is installed — never a hardcoded
# /Users/<name>/ora path, which is neither cross-platform nor a safe default.
_ORA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from slash_command_registry import (
    categories as registry_categories,
    find_command,
    iter_visible_specs,
    project_command_specs,
    runtime_command_names,
)


# Search roots for path resolution + default output dirs come from the single
# cross-platform source (honor ORA_HOME / ORA_VAULT), not hardcoded ~/ paths.
# Guarded import mirrors the other orchestrator modules; falls back to the
# __file__-derived root + expanduser only if runtime_paths can't be imported.
try:
    try:
        import runtime_paths as _rp
    except ImportError:
        from orchestrator import runtime_paths as _rp
    ORA_DIR = os.path.join(_rp.WORKSPACE, "")
    VAULT_DIR = os.path.join(_rp.VAULT_STR, "")
except Exception:  # pragma: no cover - defensive
    ORA_DIR = os.path.join(_ORA_ROOT, "")
    VAULT_DIR = os.path.expanduser("~/Documents/vault/")
DEFAULT_INSTANCE_DIR = os.path.join(VAULT_DIR, "Corpus Instances")
DEFAULT_OUTPUT_DIR = os.path.normpath(VAULT_DIR)


KNOWN_COMMANDS = runtime_command_names()


# ---------- Public API ----------

def is_runtime_command(user_input: str) -> bool:
    """Check whether user_input begins with one of the runtime slash commands.

    The /framework command is intentionally excluded — it's handled by
    milestone_executor.run_framework_command and routes to the model-driven
    framework executor, not the mechanical runtime.

    Also returns True for project-declared slash commands surfaced via the
    project plugin convention (Reference — Ora Project Plugin Convention.md).
    """
    stripped = (user_input or "").strip()
    if not stripped.startswith("/"):
        return False
    head = stripped.split(maxsplit=1)[0].lower()
    if head in KNOWN_COMMANDS:
        return True
    # Check whether any registered project declares this slash command.
    name = head[1:]
    if not name:
        return False
    try:
        from orchestrator import project_registry as _pr
        return _pr.find_project_for_slash_command(name) is not None
    except Exception:
        return False


def run_runtime_command(user_input: str) -> str:
    """Parse and execute a runtime slash command.

    Returns a user-facing markdown string. Errors are caught and surfaced
    in the returned string rather than raising, so the chat UI always
    receives a renderable response.
    """
    stripped = (user_input or "").strip()
    try:
        argv = shlex.split(stripped)
    except ValueError as exc:
        return f"[Slash command parse error: {exc}]"
    if not argv:
        return "[Empty slash command.]"

    cmd = argv[0].lower()
    args = argv[1:]

    handlers = {
        "/help": _cmd_help,
        "/commands": _cmd_help,
        "/instance": _cmd_instance,
        "/validate": _cmd_validate,
        "/render": _cmd_render,
        "/queue": _cmd_queue,
        "/approve": _cmd_approve,
        "/deny": _cmd_deny,
        "/cleaning": _cmd_cleaning,
        "/news": _cmd_news,
        "/maintenance": _cmd_maintenance,
        "/maint": _cmd_maintenance,
        "/project-tool": _cmd_project_tool,
        "/project-list": _cmd_project_list,
        "/project-register": _cmd_project_register,
        "/project-unregister": _cmd_project_unregister,
        "/projects": _cmd_projects,
    }
    handler = handlers.get(cmd)
    if handler is None:
        # Fall through to project-declared slash commands (per Reference —
        # Ora Project Plugin Convention.md). Each registered project may
        # declare its own slash commands in its manifest's `slash_commands`
        # array; they're invoked here without a namespace prefix. On
        # collision, the first project alphabetically wins (logged).
        proj_match_text = _try_project_slash_command(cmd, args)
        if proj_match_text is not None:
            return proj_match_text
        return f"[Unknown slash command: {cmd}]"
    try:
        return handler(args)
    except Exception as exc:
        return f"[Unexpected error in {cmd}: {exc}]"


# ---------- Registry / discovery handlers ----------


def _format_command_detail(spec) -> str:
    lines = [
        f"**{spec.command}**",
        "",
        spec.summary,
        "",
        f"- **Usage:** `{spec.usage}`",
        f"- **Category:** {spec.category}",
        f"- **Where it fires:** {spec.where}",
        f"- **Keyboard-only viable:** {spec.keyboard_viable}",
    ]
    if getattr(spec, "status", "active") != "active":
        lines.append(f"- **Status:** {spec.status}")
    if spec.aliases:
        lines.append(f"- **Aliases:** {', '.join(f'`{a}`' for a in spec.aliases)}")
    if spec.mouse_path:
        lines.append(f"- **Equivalent mouse path:** {spec.mouse_path}")
    if spec.notes:
        lines.append(f"- **Notes:** {spec.notes}")
    return "\n".join(lines)


def _cmd_help(args: list[str]) -> str:
    """`/help [command-or-category]` — list commands or show detail."""
    if args:
        target = " ".join(args).strip()
        category_matches = [] if target.startswith("/") else _commands_for_category(target)
        if category_matches:
            return _format_command_list(category_matches, title=f"{target.title()} commands")
        spec = _find_command(target)
        if spec is not None:
            return _format_command_detail(spec)
        return (
            f"[No slash command or category named `{target}`. "
            f"Categories: {', '.join(_registry_categories())}.]"
        )

    return _format_command_list(_iter_visible_specs(), title="Ora slash commands")


def _format_command_list(specs, title: str) -> str:
    grouped: dict[str, list] = {}
    for spec in specs:
        grouped.setdefault(spec.category, []).append(spec)

    lines = [f"**{title}**", ""]
    for category in sorted(grouped):
        lines.append(f"**{category}**")
        for spec in sorted(grouped[category], key=lambda s: s.command):
            suffix = ""
            if spec.aliases:
                suffix = " (aliases: " + ", ".join(f"`{a}`" for a in spec.aliases) + ")"
            lines.append(f"- `{spec.command}` - {spec.summary}{suffix}")
        lines.append("")
    lines.append("Use `/help <command>` for details, e.g. `/help /framework`.")
    return "\n".join(lines).rstrip()


def _project_command_specs() -> list:
    try:
        return project_command_specs(_project_registry().list_projects())
    except Exception:
        return []


def _iter_visible_specs() -> list:
    return list(iter_visible_specs()) + [
        spec for spec in _project_command_specs()
        if spec.status != "hidden"
    ]


def _commands_for_category(category: str) -> list:
    wanted = (category or "").strip().lower()
    return [
        spec for spec in _iter_visible_specs()
        if spec.category.lower() == wanted
    ]


def _find_command(token: str):
    spec = find_command(token)
    if spec is not None:
        return spec
    name = (token or "").strip().lower()
    if name and not name.startswith("/"):
        name = "/" + name
    for project_spec in _project_command_specs():
        if project_spec.command == name:
            return project_spec
    return None


def _registry_categories() -> list[str]:
    return sorted({
        *registry_categories(),
        *(spec.category for spec in _project_command_specs()),
    })


def _cmd_maintenance(args: list[str]) -> str:
    """Grouped maintenance command aliases."""
    if not args or args[0].lower() in ("help", "-h", "--help"):
        return _cmd_help(["maintenance"])
    sub = args[0].lower()
    rest = args[1:]
    if sub == "review":
        if not rest:
            return _cmd_queue([])
        sub = rest[0].lower()
        rest = rest[1:]
    if sub in ("queue", "status"):
        return _cmd_queue(rest)
    if sub == "approve":
        return _cmd_approve(rest)
    if sub == "deny":
        return _cmd_deny(rest)
    if sub == "cleaning":
        return _cmd_cleaning(rest)
    if sub == "news":
        return _cmd_news(rest)
    return (
        f"[Unknown maintenance command `{sub}`. "
        "Use `/maintenance help` for options.]"
    )


def _cmd_projects(args: list[str]) -> str:
    """Grouped project plugin command aliases."""
    if not args:
        return _cmd_project_list([])
    sub = args[0].lower()
    rest = args[1:]
    if sub in ("help", "-h", "--help"):
        return _cmd_help(["projects"])
    if sub == "list":
        return _cmd_project_list(rest)
    if sub == "register":
        return _cmd_project_register(rest)
    if sub == "unregister":
        return _cmd_project_unregister(rest)
    if sub == "tool":
        return _cmd_project_tool(rest)
    return (
        f"[Unknown projects command `{sub}`. "
        "Use `/projects help` for options.]"
    )


def _project_registry():
    try:
        from orchestrator import project_registry as _pr
        return _pr
    except Exception:
        import project_registry as _pr
        return _pr


# ---------- Project plugin command handlers (project-agnostic) ----------


def _cmd_project_tool(args: list[str]) -> str:
    """`/project-tool <nexus> <tool-name> [<json-stdin>]` — invoke a project tool.

    For argv-stdout-json tools, additional positional args after the tool name
    pass through to the tool's argv. For stdin-stdout-json tools, the third
    arg (when present) is parsed as JSON and piped to stdin. Tool output
    (JSON) is rendered as a fenced code block.
    """
    import json as _json
    _pr = _project_registry()
    if len(args) < 2:
        return ("Usage: /project-tool <nexus> <tool-name> [<args-or-stdin-json>]\n"
                "Use /project-list to see registered projects and their tools.")
    nexus, tool_name, *rest = args
    try:
        project = _pr.get_project(nexus)
    except Exception as exc:
        return f"[/project-tool: error loading project {nexus!r}: {exc}]"
    if project is None:
        return f"[/project-tool: no project registered with nexus {nexus!r}]"
    tool = project.tools.get(tool_name)
    if tool is None:
        return (f"[/project-tool: project {nexus!r} has no tool {tool_name!r}; "
                f"available: {sorted(project.tools.keys())}]")
    try:
        if tool.interface == _pr.TOOL_INTERFACE_STDIN_STDOUT:
            stdin_obj = _json.loads(rest[0]) if rest else {}
            result = _pr.invoke_project_tool(nexus, tool_name, stdin_json=stdin_obj)
        else:
            result = _pr.invoke_project_tool(nexus, tool_name, args=rest)
    except _pr.ToolInvocationError as exc:
        body = (f"```\n{exc.stderr}\n```" if getattr(exc, "stderr", "") else "")
        return f"[/project-tool: {exc}]\n{body}"
    except Exception as exc:
        return f"[/project-tool: {exc}]"
    if result is None:
        return f"[/project-tool: {nexus}:{tool_name} completed (no output)]"
    return f"```json\n{_json.dumps(result, indent=2, ensure_ascii=False)}\n```"


def _cmd_project_list(args: list[str]) -> str:
    """`/project-list` — list all registered projects."""
    _pr = _project_registry()
    projects = _pr.list_projects()
    if not projects:
        return ("No projects registered. Use /project-register <path-to-project-root> "
                "to register one.")
    lines = ["**Registered projects:**", ""]
    for p in projects:
        tools_str = ", ".join(sorted(p.tools.keys())) or "(none)"
        sc_str = ", ".join(sorted(p.slash_commands.keys())) or "(none)"
        lines.append(f"- **{p.nexus}** ({p.name}, v{p.version})")
        lines.append(f"  - root: `{p.root}`")
        lines.append(f"  - tools: {tools_str}")
        lines.append(f"  - slash commands: {sc_str}")
    return "\n".join(lines)


def _cmd_project_register(args: list[str]) -> str:
    """`/project-register <path-to-project-root>` — register a project."""
    _pr = _project_registry()
    if len(args) != 1:
        return "Usage: /project-register <path-to-project-root>"
    try:
        project = _pr.register_project(args[0])
    except _pr.ManifestError as exc:
        return f"[/project-register: invalid project — {exc}]"
    except Exception as exc:
        return f"[/project-register: {exc}]"
    return (f"Registered project **{project.nexus}** ({project.name}) "
            f"at `{project.root}`. {len(project.tools)} tool(s), "
            f"{len(project.slash_commands)} slash command(s).")


def _cmd_project_unregister(args: list[str]) -> str:
    """`/project-unregister <nexus>` — drop a project's pointer file."""
    _pr = _project_registry()
    if len(args) != 1:
        return "Usage: /project-unregister <nexus>"
    if _pr.unregister_project(args[0]):
        return f"Unregistered project **{args[0]}**. (Project files on disk untouched.)"
    return f"[/project-unregister: no project named {args[0]!r} was registered]"


def _try_project_slash_command(cmd: str, args: list[str]) -> Optional[str]:
    """Resolve `/<name>` against project-declared slash commands.

    Returns the command's output when a match is found, or None when no
    project declares the command (so the caller can fall through to the
    standard "unknown command" branch).
    """
    if not cmd.startswith("/"):
        return None
    name = cmd[1:]
    try:
        _pr = _project_registry()
        project = _pr.find_project_for_slash_command(name)
    except Exception as exc:
        return f"[/{name}: project-registry error: {exc}]"
    if project is None:
        return None
    return _pr.invoke_project_slash_command(project.nexus, name, args=args)


# ---------- Path helpers ----------

def _resolve_input_path(path: str) -> Optional[str]:
    """Resolve an input file path. Returns absolute path if found, else None.

    Search order: absolute → cwd → vault → ora.
    """
    if not path:
        return None
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return expanded if os.path.isfile(expanded) else None
    for base in (os.getcwd(), VAULT_DIR, ORA_DIR):
        candidate = os.path.join(base, expanded)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def _resolve_output_dir(path: str, default: str) -> str:
    """Resolve an output directory path. Returns absolute path.

    A blank path falls back to the default. Relative paths resolve against
    the vault, since vault is the canonical destination for produced
    artifacts. The directory is not required to exist — c_instance and
    o_render both call os.makedirs for their target directories.
    """
    if not path:
        return default
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.abspath(os.path.join(VAULT_DIR, expanded))


# ---------- Command handlers ----------

def _cmd_instance(args: list[str]) -> str:
    if len(args) < 2:
        return (
            "**Usage:** `/instance <template> <period> [<instance-dir>]`\n\n"
            "Creates a corpus instance from a template for the given period. "
            f"If `<instance-dir>` is omitted, defaults to `{DEFAULT_INSTANCE_DIR}`."
        )
    template_arg = args[0]
    period = args[1]
    instance_dir_arg = args[2] if len(args) > 2 else ""

    template_path = _resolve_input_path(template_arg)
    if template_path is None:
        return (
            f"[Template not found: `{template_arg}`. Tried absolute path, "
            f"cwd, vault (`{VAULT_DIR}`), and ora (`{ORA_DIR}`).]"
        )

    instance_dir = _resolve_output_dir(instance_dir_arg, DEFAULT_INSTANCE_DIR)

    from corpus_runtime import c_instance
    result = c_instance(template_path, period, instance_dir)
    if not result.success:
        return f"[Instance creation failed: {result.error}]"

    sections = ", ".join(result.sections_created) or "(none)"
    return (
        "**Corpus instance created.**\n\n"
        f"- **Template:** `{os.path.basename(template_path)}`\n"
        f"- **Period:** `{period}`\n"
        f"- **Instance:** `{result.instance_path}`\n"
        f"- **Sections ({len(result.sections_created)}):** {sections}\n"
    )


def _cmd_validate(args: list[str]) -> str:
    if not args:
        return (
            "**Usage:** `/validate <instance> [<template>]`\n\n"
            "Validates a populated corpus instance. The template is auto-resolved "
            "from the instance frontmatter when `<template>` is omitted."
        )
    instance_arg = args[0]
    template_arg = args[1] if len(args) > 1 else ""

    instance_path = _resolve_input_path(instance_arg)
    if instance_path is None:
        return f"[Instance not found: `{instance_arg}`.]"

    template_path: Optional[str] = None
    if template_arg:
        template_path = _resolve_input_path(template_arg)
        if template_path is None:
            return f"[Template not found: `{template_arg}`.]"

    from corpus_runtime import c_validate
    result = c_validate(instance_path, template_path=template_path)

    lines = [
        f"**Validation:** {result.overall_status} "
        f"({result.populated_count}/{result.total_count} populated)"
    ]
    if result.error:
        lines.append("")
        lines.append(f"**Error:** {result.error}")
    if result.sections:
        lines.append("")
        for s in result.sections:
            mark = "✓" if s.populated else "✗"
            lines.append(f"- {mark} **{s.section_id}** — {s.notes}")
    if result.missing_sections:
        lines.append("")
        lines.append(f"**Missing sections:** {', '.join(result.missing_sections)}")
    return "\n".join(lines)


def _cmd_render(args: list[str]) -> str:
    if len(args) < 2:
        return (
            "**Usage:** `/render <off-spec> <instance> [<output-dir>]`\n\n"
            "Renders a corpus instance through a bespoke OFF spec. "
            f"If `<output-dir>` is omitted, defaults to `{DEFAULT_OUTPUT_DIR}`."
        )
    off_spec_arg = args[0]
    instance_arg = args[1]
    output_dir_arg = args[2] if len(args) > 2 else ""

    off_path = _resolve_input_path(off_spec_arg)
    if off_path is None:
        return f"[OFF spec not found: `{off_spec_arg}`.]"
    instance_path = _resolve_input_path(instance_arg)
    if instance_path is None:
        return f"[Instance not found: `{instance_arg}`.]"

    output_dir = _resolve_output_dir(output_dir_arg, DEFAULT_OUTPUT_DIR)

    from output_runtime import o_render
    result = o_render(off_path, instance_path, output_dir)
    if not result.success:
        return f"[Render failed: {result.error}]"

    sections = ", ".join(result.sections_read) or "(none)"
    return (
        "**Output rendered.**\n\n"
        f"- **OFF spec:** `{os.path.basename(off_path)}`\n"
        f"- **Instance:** `{os.path.basename(instance_path)}`\n"
        f"- **Format:** {result.artifact_format}\n"
        f"- **Artifact:** `{result.artifact_path}`\n"
        f"- **Sections rendered ({len(result.sections_read)}):** {sections}"
    )


def _cmd_queue(args: list[str]) -> str:
    # Reserved for future flags (e.g. --redefinition-only); ignored for now.
    _ = args
    from redefinition_handler import list_pending_escalations
    entries = list_pending_escalations(redefinition_only=False)
    if not entries:
        return "**Human queue is empty.** No pending escalations awaiting review."

    word = "entry" if len(entries) == 1 else "entries"
    lines = [f"**Human queue:** {len(entries)} pending {word}", ""]
    for e in entries:
        kind = "redefinition" if e.redefinition else "escalation"
        project = e.event.get("project_nexus") or "(none)"
        reasoning = (e.verdict.get("reasoning") or "").strip()
        if len(reasoning) > 240:
            reasoning = reasoning[:240].rstrip() + "…"
        lines.append(
            f"- **[{e.queue_index}]** {kind} — project `{project}` — "
            f"queued {e.queued_at}"
        )
        if reasoning:
            lines.append(f"    > {reasoning}")
        if e.forced_reason:
            lines.append(f"    *Forced reason:* {e.forced_reason}")
    lines.append("")
    lines.append(
        "Use `/approve <index>` or `/deny <index> [<reason>]` to act on a "
        "redefinition entry."
    )
    return "\n".join(lines)


def _maybe_resolve_gate_entry_at(idx: int, approve: bool,
                                 reason: str = "") -> str | None:
    """Kind-dispatch for /approve and /deny: Execution Review gate entries
    (kind=execution_gate) resolve through tool_events, never through
    redefinition_handler. Returns None for non-gate entries."""
    try:
        import json as _json
        # Resolve the SAME effective file the legacy path (redefinition_handler
        # -> oversight_actions.human_queue_path()) indexes, so /approve and
        # /deny address one consistent view of the queue under any
        # monkeypatch or ORA_OVERSIGHT_SANDBOX redirection.
        from oversight_actions import human_queue_path, file_lock
        queue_path = human_queue_path()
        if not os.path.isfile(queue_path):
            return None
        with open(queue_path) as f:
            lines = [l for l in f if l.strip()]
        if idx < 0 or idx >= len(lines):
            return None
        rec = _json.loads(lines[idx])
        _kind = rec.get("kind")
        if _kind not in ("execution_gate", "task_gate"):
            return None
        if _kind == "task_gate":
            # Execution Review Phase 2: irreversible-tier task hold.
            try:
                import risk_gate
            except ImportError:
                from orchestrator import risk_gate
            message = risk_gate.resolve_task_gate_entry(rec, approve=approve,
                                                        reason=reason)
        else:
            try:
                import tool_events
            except ImportError:
                from orchestrator import tool_events
            message = tool_events.resolve_gate_entry(rec, approve=approve,
                                                     reason=reason)
        with file_lock(queue_path):
            with open(queue_path) as f:
                current = [l for l in f if l.strip()]
            if idx < len(current) and current[idx] == lines[idx]:
                del current[idx]
                with open(queue_path, "w") as f:
                    f.writelines(current)
        return message
    except Exception:
        # Any failure inspecting the entry falls through to the legacy
        # redefinition path — this helper must never hijack a normal
        # /approve//deny on a non-gate entry.
        return None


def _cmd_approve(args: list[str]) -> str:
    if not args:
        return (
            "**Usage:** `/approve <index> [<proposed-definition>]`\n\n"
            "Approves a pending redefinition. Use `/queue` to list available indexes. "
            "If `<proposed-definition>` is omitted, the verdict's redefinition payload "
            "is used as the new problem definition."
        )
    try:
        idx = int(args[0])
    except ValueError:
        return f"[`{args[0]}` is not a valid index. Use `/queue` to list indexes.]"
    proposed = " ".join(args[1:]) if len(args) > 1 else None

    gate_msg = _maybe_resolve_gate_entry_at(idx, approve=True)
    if gate_msg is not None:
        return gate_msg

    from redefinition_handler import approve_redefinition
    result = approve_redefinition(idx, proposed)
    if not result.success:
        return f"[Approval failed: {result.error}]"

    return (
        "**Redefinition applied.**\n\n"
        f"- **Archived PED:** `{result.archived_path}`\n"
        f"- **New PED:** `{result.new_ped_path}`\n"
        f"- **Re-evaluation queued:** `{result.reeval_task_id}`"
    )


def _cmd_deny(args: list[str]) -> str:
    if not args:
        return (
            "**Usage:** `/deny <index> [<reason>]`\n\n"
            "Denies a pending redefinition. Use `/queue` to list available indexes."
        )
    try:
        idx = int(args[0])
    except ValueError:
        # `/deny credential_store:<service>` revokes a standing allow
        # granted through an execution-gate approval.
        if ":" in args[0]:
            try:
                import tool_events
            except ImportError:
                from orchestrator import tool_events
            if tool_events.revoke_standing_allow(args[0]):
                return f"**Standing allow revoked** for `{args[0]}`."
            return f"[No active standing allow found for `{args[0]}`.]"
        return f"[`{args[0]}` is not a valid index. Use `/queue` to list indexes.]"
    reason = " ".join(args[1:]) if len(args) > 1 else ""

    gate_msg = _maybe_resolve_gate_entry_at(idx, approve=False, reason=reason)
    if gate_msg is not None:
        return gate_msg

    from redefinition_handler import deny_redefinition
    result = deny_redefinition(idx, reason)
    if not result.success:
        return f"[Denial failed: {result.error}]"

    suffix = f" Reason: {reason}" if reason else ""
    return f"**Denial recorded.** Queue entry {idx} removed.{suffix}"


# ---------- /cleaning — Engram Cleaning Framework ----------


_CLEANING_QUEUE_FILE = os.path.join(_rp.VAULT_ORA_STR, "Working — Engram Cleaning Queue.md")


def _cleaning_queue_status() -> tuple[int, int, str]:
    """Return (total_pairs, pending_count, last_modified) from the queue file.

    Pending status is read from each pair's `**Resolution:** [marker]` line —
    the user-facing edit point. The heading marker (`## [pending] ...`) is
    informational only.
    """
    if not os.path.exists(_CLEANING_QUEUE_FILE):
        return 0, 0, ""
    with open(_CLEANING_QUEUE_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    import re as _re
    markers = _re.findall(r"\*\*Resolution:\*\*\s*\[([^\]]+)\]", text)
    pending = sum(1 for m in markers if m.strip() == "pending")
    from datetime import datetime as _dt
    mtime = os.path.getmtime(_CLEANING_QUEUE_FILE)
    return len(markers), pending, _dt.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def _cmd_cleaning(args: list[str]) -> str:
    sub = args[0].lower() if args else "status"

    if sub in ("help", "-h", "--help"):
        return (
            "**Engram Cleaning Framework**\n\n"
            "- `/cleaning status` — queue state\n"
            "- `/cleaning detect [strategy] [limit] [--include-skipped]` — produce triage queue\n"
            "    strategies: `bidirectional` (default), `date-gap`, `random`\n"
            "    limit: max pairs to surface (default 25)\n"
            "    `--include-skipped`: re-surface previously-resolved pairs\n"
            "- `/cleaning resolve [--apply]` — apply marked resolutions\n"
            "    dry-run by default; pass `--apply` to mutate vault\n\n"
            "See `Framework — Engram Cleaning` for the full spec."
        )

    if sub == "status":
        total, pending, mtime = _cleaning_queue_status()
        if total == 0:
            return (
                "**Engram Cleaning queue is empty.**\n\n"
                "Run `/cleaning detect` to produce a triage queue."
            )
        resolved = total - pending
        return (
            f"**Engram Cleaning queue:** {total} pairs total, "
            f"{pending} pending, {resolved} resolved.\n\n"
            f"- Last modified: {mtime}\n"
            f"- File: `Working — Engram Cleaning Queue.md`\n\n"
            "Edit each pending pair's Resolution line, then "
            "`/cleaning resolve --apply` to mutate vault."
        )

    if sub == "detect":
        # Strip optional flags so positional parsing isn't confused
        include_skipped = "--include-skipped" in args
        positional = [a for a in args if not a.startswith("--")]

        strategy = positional[1] if len(positional) > 1 else "bidirectional"
        if strategy not in ("bidirectional", "date-gap", "random"):
            return (
                f"[Unknown strategy `{strategy}`. Valid: `bidirectional`, "
                f"`date-gap`, `random`.]"
            )
        try:
            limit = int(positional[2]) if len(positional) > 2 else 25
        except ValueError:
            return f"[`{positional[2]}` is not a valid integer for limit.]"
        if not (1 <= limit <= 200):
            return "[Limit must be between 1 and 200.]"

        try:
            from historical.run_engram_cleaning_detection import run_detection
        except ImportError:
            # Fall back: try via orchestrator package path
            import sys as _sys
            _sys.path.insert(0, _ORA_ROOT)
            from orchestrator.historical.run_engram_cleaning_detection import run_detection

        result = run_detection(
            strategy=strategy, limit=limit, write_queue=True,
            include_skipped=include_skipped,
        )
        filter_line = ""
        if not include_skipped:
            filter_line = (
                f"- **Resolved pairs filtered from log:** "
                f"{result.get('resolved_filtered_count', 0)}\n"
            )
        return (
            "**Engram Cleaning detection complete.**\n\n"
            f"- **Strategy:** `{result['strategy']}`\n"
            f"- **Engrams scanned:** {result['engram_count']}\n"
            f"{filter_line}"
            f"- **Pairs surfaced:** {result['pairs_count']}\n"
            f"- **Queue file:** `{os.path.basename(result['queue_path'])}` "
            f"(at vault root)\n\n"
            "Open the queue file, edit each pair's Resolution line "
            "(`[changed-mind:...]`, `[wrong:source]`, `[hypocrisy]`, `[skip]`, etc.), "
            "then `/cleaning resolve --apply` to mutate the vault."
        )

    if sub == "resolve":
        apply = "--apply" in args
        dry_run = not apply

        try:
            from historical.run_engram_cleaning_resolver import run_resolver
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, _ORA_ROOT)
            from orchestrator.historical.run_engram_cleaning_resolver import run_resolver

        try:
            result = run_resolver(dry_run=dry_run)
        except FileNotFoundError as exc:
            return f"[{exc}. Run `/cleaning detect` first.]"

        stats = result["stats"]
        non_pending_total = sum(v for k, v in stats.items() if k != "pending")
        if non_pending_total == 0:
            return (
                f"**No resolutions marked.** All {stats.get('pending', 0)} pairs are "
                "still `[pending]`. Edit the queue file's Resolution lines first, "
                "then re-run `/cleaning resolve --apply`."
            )

        mode_label = "DRY RUN" if dry_run else "APPLIED"
        lines = [f"**Engram Cleaning resolver — {mode_label}**", ""]
        for k in sorted(stats):
            if stats[k] == 0:
                continue
            lines.append(f"- {k}: {stats[k]}")
        lines.append("")
        lines.append(f"- **Affected files:** {result['affected_slugs_count']}")
        lines.append(f"- **Queue remaining:** {result['queue_remaining_count']} pending")
        if result.get("errors"):
            lines.append("")
            lines.append("**Errors:**")
            for e in result["errors"][:10]:
                lines.append(f"- {e}")
        if dry_run and non_pending_total > 0:
            lines.append("")
            lines.append("Re-run with `--apply` to commit these mutations.")
        return "\n".join(lines)

    return (
        f"[Unknown subcommand `{sub}`. "
        "Use `/cleaning help` for usage.]"
    )


# ---------- /news — News Supersession Framework ----------


_NEWS_QUEUE_FILE = os.path.join(_rp.VAULT_ORA_STR, "Working — News Supersession Queue.md")


def _news_queue_status() -> tuple[int, int, str]:
    """Return (total_pairs, pending_count, last_modified) from the queue file.

    Pending status is read from each pair's `**Resolution:** [marker]` line.
    """
    if not os.path.exists(_NEWS_QUEUE_FILE):
        return 0, 0, ""
    with open(_NEWS_QUEUE_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    import re as _re
    markers = _re.findall(r"\*\*Resolution:\*\*\s*\[([^\]]+)\]", text)
    pending = sum(1 for m in markers if m.strip() == "pending")
    from datetime import datetime as _dt
    mtime = os.path.getmtime(_NEWS_QUEUE_FILE)
    return len(markers), pending, _dt.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def _cmd_news(args: list[str]) -> str:
    sub = args[0].lower() if args else "status"

    if sub in ("help", "-h", "--help"):
        return (
            "**News Supersession Framework**\n\n"
            "- `/news status` — queue state\n"
            "- `/news detect [strategy] [limit] [--similarity T] [--include-resolved]` — produce triage queue\n"
            "    strategies: `topic-cluster` (default), `recent`, `random`\n"
            "    limit: max pairs to surface (default 25)\n"
            "    `--similarity`: cosine threshold for topic clustering (default 0.80)\n"
            "    `--include-resolved`: re-surface previously-resolved pairs\n"
            "- `/news resolve [--apply]` — apply marked resolutions\n"
            "    dry-run by default; pass `--apply` to mutate vault\n\n"
            "See `Framework — News Supersession` for the full spec. Key distinction "
            "from `/cleaning`: `[changed-mind:*]` markers apply the `superseded` tag "
            "(weight modifier, preserves retrieval at reduced weight) rather than "
            "`archived` (filter, excludes from default retrieval). News stories "
            "develop but they don't replace history."
        )

    if sub == "status":
        total, pending, mtime = _news_queue_status()
        if total == 0:
            return (
                "**News Supersession queue is empty.**\n\n"
                "Run `/news detect` to produce a triage queue."
            )
        resolved = total - pending
        return (
            f"**News Supersession queue:** {total} pairs total, "
            f"{pending} pending, {resolved} resolved.\n\n"
            f"- Last modified: {mtime}\n"
            f"- File: `Working — News Supersession Queue.md`\n\n"
            "Edit each pending pair's Resolution line, then "
            "`/news resolve --apply` to mutate vault."
        )

    if sub == "detect":
        # Strip optional flags so positional parsing isn't confused
        include_resolved = "--include-resolved" in args
        similarity = 0.80
        # Look for --similarity T
        for i, a in enumerate(args):
            if a == "--similarity" and i + 1 < len(args):
                try:
                    similarity = float(args[i + 1])
                except ValueError:
                    return f"[`{args[i+1]}` is not a valid float for similarity.]"

        positional = [
            a for i, a in enumerate(args)
            if not a.startswith("--") and (i == 0 or not args[i-1] == "--similarity")
        ]

        strategy = positional[1] if len(positional) > 1 else "topic-cluster"
        if strategy not in ("topic-cluster", "recent", "random"):
            return (
                f"[Unknown strategy `{strategy}`. "
                "Valid: `topic-cluster`, `recent`, `random`.]"
            )
        try:
            limit = int(positional[2]) if len(positional) > 2 else 25
        except ValueError:
            return f"[`{positional[2]}` is not a valid integer for limit.]"
        if not (1 <= limit <= 200):
            return "[Limit must be between 1 and 200.]"

        try:
            from historical.run_news_supersession_detection import run_detection
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, _ORA_ROOT)
            from orchestrator.historical.run_news_supersession_detection import (
                run_detection,
            )

        result = run_detection(
            strategy=strategy,
            limit=limit,
            similarity=similarity,
            write_queue=True,
            include_resolved=include_resolved,
        )
        filter_line = ""
        if not include_resolved:
            filter_line = (
                f"- **Resolved pairs filtered from log:** "
                f"{result.get('resolved_filtered_count', 0)}\n"
            )
        return (
            "**News Supersession detection complete.**\n\n"
            f"- **Strategy:** `{result['strategy']}`\n"
            f"- **Similarity threshold:** {result['similarity']}\n"
            f"- **Eligible resources scanned:** {result['resource_count']}\n"
            f"{filter_line}"
            f"- **Pairs surfaced:** {result['pairs_count']}\n"
            f"- **Queue file:** `{os.path.basename(result['queue_path'])}` "
            f"(at vault root)\n\n"
            "Open the queue file, edit each pair's Resolution line "
            "(`[changed-mind:...]`, `[wrong:source]`, `[skip]`, etc.), "
            "then `/news resolve --apply` to mutate the vault."
        )

    if sub == "resolve":
        apply = "--apply" in args
        dry_run = not apply

        try:
            from historical.run_news_supersession_resolver import run_resolver
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, _ORA_ROOT)
            from orchestrator.historical.run_news_supersession_resolver import (
                run_resolver,
            )

        try:
            result = run_resolver(dry_run=dry_run)
        except FileNotFoundError as exc:
            return f"[{exc}. Run `/news detect` first.]"

        stats = result["stats"]
        non_pending_total = sum(v for k, v in stats.items() if k != "pending")
        if non_pending_total == 0:
            return (
                f"**No resolutions marked.** All {stats.get('pending', 0)} pairs are "
                "still `[pending]`. Edit the queue file's Resolution lines first, "
                "then re-run `/news resolve --apply`."
            )

        mode_label = "DRY RUN" if dry_run else "APPLIED"
        lines = [f"**News Supersession resolver — {mode_label}**", ""]
        for k in sorted(stats):
            if stats[k] == 0:
                continue
            lines.append(f"- {k}: {stats[k]}")
        lines.append("")
        lines.append(f"- **Affected files:** {result['affected_slugs_count']}")
        lines.append(f"- **Queue remaining:** {result['queue_remaining_count']} pending")
        if result.get("errors"):
            lines.append("")
            lines.append("**Warnings / errors:**")
            for e in result["errors"][:10]:
                lines.append(f"- {e}")
        if dry_run and non_pending_total > 0:
            lines.append("")
            lines.append("Re-run with `--apply` to commit these mutations.")
        return "\n".join(lines)

    return (
        f"[Unknown subcommand `{sub}`. "
        "Use `/news help` for usage.]"
    )



# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python slash_commands.py '<full slash command line>'")
        print("Example: python slash_commands.py '/queue'")
        sys.exit(1)
    print(run_runtime_command(sys.argv[1]))
