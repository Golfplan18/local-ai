"""User-facing slash-command registry for Ora.

The dispatcher remains responsible for executing server-side commands. This
module is the shared catalogue: command names, categories, aliases, where they
fire, argument shapes, and discoverability metadata for help/docs/autocomplete.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class SlashCommandSpec:
    command: str
    category: str
    where: str
    summary: str
    usage: str
    keyboard_viable: str
    status: str = "active"
    aliases: tuple[str, ...] = field(default_factory=tuple)
    mouse_path: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["aliases"] = list(self.aliases)
        return data


COMMAND_SPECS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec(
        command="/help",
        aliases=("/commands",),
        category="Discovery",
        where="server",
        summary="List slash commands or show detail for one command/category.",
        usage="/help [command-or-category]",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/framework",
        category="Frameworks",
        where="framework executor",
        summary="Run or start interactive elicitation for a user-invocable framework.",
        usage="/framework <framework|alias> [--config <name>] [<mode>] [<input>]",
        mouse_path="Framework picker for selection; no exact mouse path for one-shot execution",
        keyboard_viable="Yes",
        notes="Aliases include cff, pff, and off. Internal Gear 4 F-* stages are blocked.",
    ),
    SlashCommandSpec(
        command="/instance",
        category="Runtime",
        where="server",
        summary="Create a corpus instance from a template for a period.",
        usage="/instance <template> <period> [<instance-dir>]",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/validate",
        category="Runtime",
        where="server",
        summary="Validate a populated corpus instance against its template.",
        usage="/validate <instance> [<template>]",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/render",
        category="Runtime",
        where="server",
        summary="Render a corpus instance through an OFF spec.",
        usage="/render <off-spec> <instance> [<output-dir>]",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/queue",
        category="Maintenance",
        where="server",
        summary="List human-review queue entries.",
        usage="/queue",
        mouse_path="Sidebar > Oversight > Review queue",
        keyboard_viable="Yes",
        notes="Also available as /maintenance queue.",
    ),
    SlashCommandSpec(
        command="/approve",
        category="Maintenance",
        where="server",
        summary="Approve a pending redefinition queue entry.",
        usage="/approve <index> [<proposed-definition>]",
        mouse_path="Sidebar review controls where available",
        keyboard_viable="Yes",
        notes="Also available as /maintenance approve.",
    ),
    SlashCommandSpec(
        command="/deny",
        category="Maintenance",
        where="server",
        summary="Deny a pending redefinition queue entry.",
        usage="/deny <index> [<reason>]",
        mouse_path="Sidebar review controls where available",
        keyboard_viable="Yes",
        notes="Also available as /maintenance deny.",
    ),
    SlashCommandSpec(
        command="/cleaning",
        category="Maintenance",
        where="server",
        summary="Run or inspect the Engram Cleaning queue.",
        usage="/cleaning [status|detect|resolve|help] [options]",
        mouse_path="None",
        keyboard_viable="Yes",
        notes="Also available as /maintenance cleaning.",
    ),
    SlashCommandSpec(
        command="/news",
        category="Maintenance",
        where="server",
        summary="Run or inspect the News Supersession queue.",
        usage="/news [status|detect|resolve|help] [options]",
        mouse_path="None",
        keyboard_viable="Yes",
        notes="Universal today; review whether this should become project-scoped.",
    ),
    SlashCommandSpec(
        command="/maintenance",
        aliases=("/maint",),
        category="Maintenance",
        where="server",
        summary="Grouped access to queue, review, cleaning, and news maintenance commands.",
        usage="/maintenance <queue|approve|deny|cleaning|news> [args...]",
        mouse_path="Mixed; see child commands",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/review",
        category="Maintenance",
        where="browser",
        summary="Open the full review queue panel.",
        usage="/review [paused|operating]",
        mouse_path="Sidebar > Oversight > Review queue",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/project-list",
        category="Projects",
        where="server",
        summary="List registered Ora projects and their tools/commands.",
        usage="/project-list",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/project-register",
        category="Projects",
        where="server",
        summary="Register a project plugin manifest by root path.",
        usage="/project-register <path-to-project-root>",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/project-unregister",
        category="Projects",
        where="server",
        summary="Remove a registered project's pointer file.",
        usage="/project-unregister <nexus>",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/project-tool",
        category="Projects",
        where="server",
        summary="Invoke a registered project tool.",
        usage="/project-tool <nexus> <tool-name> [<args-or-stdin-json>]",
        mouse_path="None",
        keyboard_viable="Yes",
        status="blocked",
        notes=(
            "Currently refuses every invocation. The handler routes through "
            "system_protection.authorize_server_action('project_tool_execute', "
            "…), and that action has no entry in "
            "SERVER_ACTION_SELECTOR_PREFIXES, so authorization is denied "
            "before the tool runs. The denial is deliberate and test-asserted "
            "(test_g1_22a_system_protection.py :: "
            "test_opaque_server_and_slash_actions_have_no_adapter); writing "
            "the missing adapter is G1.22A work, because it changes an "
            "authority boundary. Until then, reach a project tool through a "
            "Trigger, which carries its own exact-digest activation review."
        ),
    ),
    SlashCommandSpec(
        command="/projects",
        category="Projects",
        where="server",
        summary="Grouped access to project plugin commands.",
        usage="/projects <list|register|unregister|tool> [args...]",
        mouse_path="None",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/new",
        category="Navigation",
        where="browser",
        summary="Start a new Dialogue.",
        usage="/new",
        mouse_path="Spine plus button or sidebar New Dialogue",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/sidebar",
        category="Navigation",
        where="browser",
        summary="Open, close, or toggle the Dialogue sidebar.",
        usage="/sidebar [open|close|toggle]",
        mouse_path="Spine sidebar toggle or A wordmark",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/frameworks",
        category="Navigation",
        where="browser",
        summary="Open the framework picker or stage a named framework for the next prompt.",
        usage="/frameworks [framework|alias]",
        mouse_path="Input toolbar > Framework",
        keyboard_viable="Yes",
        notes="Use `/framework` for one-shot framework execution; `/frameworks cff` only stages the picker selection.",
    ),
    SlashCommandSpec(
        command="/modes",
        aliases=("/mode", "/analyses", "/analysis"),
        category="Navigation",
        where="browser",
        summary="Open the analysis mode picker or stage a named analysis mode for the next prompt.",
        usage="/modes [mode-id-or-name]",
        mouse_path="Input toolbar > Analysis",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/settings",
        category="Navigation",
        where="browser",
        summary="Open settings, optionally to a named tab.",
        usage="/settings [models|visual|projects|shortcuts|apis|interface|capture|export|transcription|speech]",
        mouse_path="Spine settings button",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/visual",
        aliases=("/canvas",),
        category="Visual",
        where="browser",
        summary="Return the right pane to the Exhibits canvas.",
        usage="/visual",
        mouse_path="Exit video pane mode, when active",
        keyboard_viable="Partial",
        notes="The current UI has a canvas/video pane-mode toggle, not a generic hide/show visual-pane toggle.",
    ),
    SlashCommandSpec(
        command="/video",
        category="Visual",
        where="browser",
        summary="Toggle video pane mode.",
        usage="/video [on|off|toggle]",
        mouse_path="Spine video button",
        keyboard_viable="Yes",
    ),
    SlashCommandSpec(
        command="/dismiss",
        category="Runtime",
        where="server",
        summary="Clear a review-queue card that can no longer be resolved.",
        usage="/dismiss <index>",
        mouse_path="Sidebar > Oversight > Review queue > card > Dismiss",
        keyboard_viable="Yes",
        notes=(
            "For execution-gate cards whose approval request is already "
            "spent: both Approve and Deny dead-end on those, so without this "
            "the queue could only grow. A card that can still be resolved is "
            "refused — dismissing is not a third verdict and grants nothing."
        ),
    ),
    SlashCommandSpec(
        command="/trigger",
        aliases=("/triggers",),
        category="Runtime",
        where="server",
        summary="Author, review, and control scheduled or event-driven work.",
        usage=(
            "/trigger list | show <id> | create <flags> | "
            "activate <id> [--approve <digest>] | pause|resume|retire|run <id>"
        ),
        mouse_path="Sidebar > Oversight > Scheduled",
        keyboard_viable="Yes",
        notes=(
            "A Trigger activates an already-registered project tool or "
            "framework; it never carries a command string. Causes are manual, "
            "file change, calendar, and completion of another Trigger. A "
            "calendar Trigger needs a written runtime-impossibility "
            "justification (--because) before it can be activated."
        ),
    ),
    SlashCommandSpec(
        command="/image",
        aliases=("/generate-image",),
        category="Visual",
        where="browser",
        summary="Generate an image from a prompt, or arm image generation for the next prompt.",
        usage="/image [prompt]",
        mouse_path="Input toolbar > Image generation toggle",
        keyboard_viable="Yes",
    ),
)


SERVER_COMMANDS = {
    spec.command for spec in COMMAND_SPECS if spec.where == "server"
}

SERVER_ALIASES = {
    alias: spec.command
    for spec in COMMAND_SPECS
    if spec.where == "server"
    for alias in spec.aliases
}


def all_command_specs() -> tuple[SlashCommandSpec, ...]:
    return COMMAND_SPECS


def project_command_specs(projects: Iterable) -> list[SlashCommandSpec]:
    """Build discovery specs for slash commands declared by projects.

    Project commands are installation-specific. They are intentionally not
    added to ``COMMAND_SPECS`` or ``runtime_command_names``; the dispatcher
    resolves them dynamically through project_registry after core commands.
    """
    specs: list[SlashCommandSpec] = []
    core_names = {spec.command for spec in COMMAND_SPECS}
    core_aliases = {
        alias for spec in COMMAND_SPECS for alias in spec.aliases
    }
    seen: dict[str, str] = {}
    for project in projects or []:
        nexus = getattr(project, "nexus", "") or ""
        project_name = getattr(project, "name", "") or nexus or "Project"
        commands = getattr(project, "slash_commands", {}) or {}
        for cmd in sorted(commands.values(), key=lambda c: c.name):
            name = "/" + cmd.name.lstrip("/")
            notes = f"Declared by project {project_name} ({nexus})."
            status = "project-specific"
            if name in core_names or name in core_aliases:
                status = "shadowed"
                notes += " This name collides with a core command and will not fire as a project command."
            elif name in seen:
                status = "shadowed"
                notes += f" This name is also declared by {seen[name]}; first project by registry order wins."
            else:
                seen[name] = nexus or project_name
            specs.append(SlashCommandSpec(
                command=name,
                category="Project Commands",
                where="server",
                summary=cmd.description or f"Run {project_name} project command.",
                usage=f"{name} [args...]",
                mouse_path="None",
                keyboard_viable="Yes",
                status=status,
                notes=notes,
            ))
    return specs


def registry_payload(projects: Iterable | None = None) -> dict:
    specs = list(COMMAND_SPECS)
    if projects is not None:
        specs.extend(project_command_specs(projects))
    return {"commands": [spec.to_dict() for spec in specs]}


def runtime_command_names() -> set[str]:
    return set(SERVER_COMMANDS) | set(SERVER_ALIASES)


def find_command(token: str) -> SlashCommandSpec | None:
    name = (token or "").strip().lower()
    if not name:
        return None
    if not name.startswith("/"):
        name = "/" + name
    for spec in COMMAND_SPECS:
        if spec.command == name or name in spec.aliases:
            return spec
    return None


def categories() -> list[str]:
    return sorted({spec.category for spec in COMMAND_SPECS})


def commands_for_category(category: str) -> list[SlashCommandSpec]:
    wanted = (category or "").strip().lower()
    return [
        spec for spec in COMMAND_SPECS
        if spec.category.lower() == wanted
    ]


def iter_visible_specs() -> Iterable[SlashCommandSpec]:
    return (spec for spec in COMMAND_SPECS if spec.status != "hidden")
