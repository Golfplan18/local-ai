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
      Default output-dir: ~/Documents/vault/Outputs/

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

  /hector-render <recipe.json>
      Render a Hector editorial cartoon from a Layers 1-5 framework recipe.
      Operationalizes Framework — MSI Hector Rentier Editorial Cartoon
      Layers 6-8: prompt construction → image generation → vectorization
      → SVG text overlays → Astro column .md emission.

  /news-image-render <request.json>
      Render a news article image from the article generator's image
      request. Operationalizes Framework — News Image Generator Layers 3-5
      along the AI path: likeness gate → prompt construction → image
      generation → article .md image-field patch.

Path resolution for input files: absolute path is tried first, then
relative-to-cwd, relative-to-vault, relative-to-ora. The first hit wins.

Per Reference — Meta-Layer Architecture; the deferred runtime-invocation
slash commands listed in the 2026-05-04 implementation handoff §"Genuinely
Deferred (Next Session)" item 1.
"""
from __future__ import annotations

import os
import shlex
from typing import Optional


VAULT_DIR = os.path.expanduser("~/Documents/vault/")
ORA_DIR = os.path.expanduser("~/ora/")
DEFAULT_INSTANCE_DIR = os.path.join(VAULT_DIR, "Corpus Instances")
DEFAULT_OUTPUT_DIR = os.path.join(VAULT_DIR, "Outputs")

KNOWN_COMMANDS = {"/instance", "/validate", "/render", "/queue", "/approve",
                  "/deny", "/cleaning", "/news",
                  "/hector-render", "/news-image-render"}


# ---------- Public API ----------

def is_runtime_command(user_input: str) -> bool:
    """Check whether user_input begins with one of the runtime slash commands.

    The /framework command is intentionally excluded — it's handled by
    milestone_executor.run_framework_command and routes to the model-driven
    framework executor, not the mechanical runtime.
    """
    stripped = (user_input or "").strip()
    if not stripped.startswith("/"):
        return False
    head = stripped.split(maxsplit=1)[0].lower()
    return head in KNOWN_COMMANDS


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
        "/instance": _cmd_instance,
        "/validate": _cmd_validate,
        "/render": _cmd_render,
        "/queue": _cmd_queue,
        "/approve": _cmd_approve,
        "/deny": _cmd_deny,
        "/cleaning": _cmd_cleaning,
        "/news": _cmd_news,
        "/hector-render": _cmd_hector_render,
        "/news-image-render": _cmd_news_image_render,
    }
    handler = handlers.get(cmd)
    if handler is None:
        return f"[Unknown slash command: {cmd}]"
    try:
        return handler(args)
    except Exception as exc:
        return f"[Unexpected error in {cmd}: {exc}]"


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
        return f"[`{args[0]}` is not a valid index. Use `/queue` to list indexes.]"
    reason = " ".join(args[1:]) if len(args) > 1 else ""

    from redefinition_handler import deny_redefinition
    result = deny_redefinition(idx, reason)
    if not result.success:
        return f"[Denial failed: {result.error}]"

    suffix = f" Reason: {reason}" if reason else ""
    return f"**Denial recorded.** Queue entry {idx} removed.{suffix}"


# ---------- /cleaning — Engram Cleaning Framework ----------


_CLEANING_QUEUE_FILE = os.path.join(VAULT_DIR, "Working — Engram Cleaning Queue.md")


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
            "    strategies: `bidirectional` (default), `random`\n"
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
        if strategy not in ("bidirectional", "random"):
            return (
                f"[Unknown strategy `{strategy}`. Valid: `bidirectional`, `random`.]"
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
            _sys.path.insert(0, "/Users/oracle/ora")
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
            _sys.path.insert(0, "/Users/oracle/ora")
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


_NEWS_QUEUE_FILE = os.path.join(VAULT_DIR, "Working — News Supersession Queue.md")


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
            _sys.path.insert(0, "/Users/oracle/ora")
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
            _sys.path.insert(0, "/Users/oracle/ora")
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


# ---------- /hector-render — Hector editorial cartoon rendering ----------


def _cmd_hector_render(args: list[str]) -> str:
    """Render a Hector cartoon from a Layers 1-5 recipe JSON file."""
    if not args:
        return (
            "**Usage:** `/hector-render <recipe.json>`\n\n"
            "Renders a Hector editorial cartoon. The recipe is the structured "
            "output of running the `MSI Hector Rentier Editorial Cartoon` "
            "framework against a news cluster — it carries the composition "
            "spec (Layer 3), caption (Layer 4), and likeness verdict (Layer 5).\n\n"
            "**Recipe schema (JSON):**\n"
            "```json\n"
            "{\n"
            '  "cluster_id": "<string>",\n'
            '  "headline": "<string>",\n'
            '  "lede": "<string>",\n'
            '  "publish_date": "<ISO-8601 date>",\n'
            '  "composition_spec": "<Layer 3 composition prose>",\n'
            '  "caption": "<Layer 4 caption, ≤15 words>",\n'
            '  "banner": "<optional Layer 4 banner text>",\n'
            '  "likeness_verdict": {...},\n'
            '  "sources": [...],\n'
            '  "metadata": {...}\n'
            "}\n"
            "```"
        )

    recipe_path = _resolve_input_path(args[0])
    if recipe_path is None:
        return (
            f"[Recipe not found: `{args[0]}`. Tried absolute path, cwd, "
            f"vault (`{VAULT_DIR}`), and ora (`{ORA_DIR}`).]"
        )

    import json
    try:
        with open(recipe_path, "r") as f:
            recipe_data = json.load(f)
    except json.JSONDecodeError as exc:
        return f"[Recipe JSON parse error: {exc}]"
    except OSError as exc:
        return f"[Could not read recipe: {exc}]"

    from msi_image_render import render_hector_cartoon
    result = render_hector_cartoon(recipe_data)

    if not result.get("success"):
        lines = [
            "**Hector cartoon render failed.**",
            "",
            f"- **Error:** {result.get('error', '<unknown>')}",
        ]
        attempts = result.get("attempts") or []
        if attempts:
            lines.append("- **Attempts:**")
            for attempt in attempts:
                marker = "✓" if attempt.get("succeeded") else "✗"
                code = attempt.get("error_code") or "<ok>"
                lines.append(
                    f"  - {marker} `{attempt.get('provider_id')}` ({code})"
                )
        return "\n".join(lines)

    lines = [
        "**Hector cartoon rendered.**",
        "",
        f"- **Slug:** `{result['slug']}`",
        f"- **Column file:** `{result['column_md_path']}`",
        f"- **SVG asset:** `{result['svg_path']}`",
        f"- **Provider:** `{result['image_schema']['ai_model']}`",
    ]
    attempts = result.get("attempts") or []
    if len(attempts) > 1:
        lines.append("- **Fallback chain:**")
        for attempt in attempts:
            marker = "✓" if attempt.get("succeeded") else "✗"
            code = attempt.get("error_code") or "ok"
            lines.append(
                f"  - {marker} `{attempt.get('provider_id')}` ({code})"
            )
    lines.append("")
    lines.append(
        "Run `npm run build` in `~/sites/mainstreetindependent/` to "
        "verify the column compiles, then `git push` to deploy."
    )
    return "\n".join(lines)


# ---------- /news-image-render — News article image rendering ----------


def _cmd_news_image_render(args: list[str]) -> str:
    """Render a news article image from an image-generation request JSON file."""
    if not args:
        return (
            "**Usage:** `/news-image-render <request.json>`\n\n"
            "Renders a news article image. The request is the structured "
            "object emitted by the News Article Generator framework "
            "alongside an article — it carries the article slug, the visual "
            "register, prompt seeds, and the entity list for the likeness "
            "gate.\n\n"
            "**Request schema (JSON):**\n"
            "```json\n"
            "{\n"
            '  "article_slug": "<string, matches articles/<slug>.md>",\n'
            '  "article_headline": "<string>",\n'
            '  "article_lede": "<string>",\n'
            '  "visual_register": "photographic|illustrated|diagrammatic",\n'
            '  "prompt_seeds": ["<seed>", ...],\n'
            '  "primary_entities": [\n'
            '    {"name": "...", "is_public_figure": true,\n'
            '     "in_public_role": true},\n'
            "    ...\n"
            "  ]\n"
            "}\n"
            "```"
        )

    request_path = _resolve_input_path(args[0])
    if request_path is None:
        return (
            f"[Request not found: `{args[0]}`. Tried absolute path, cwd, "
            f"vault (`{VAULT_DIR}`), and ora (`{ORA_DIR}`).]"
        )

    import json
    try:
        with open(request_path, "r") as f:
            request_data = json.load(f)
    except json.JSONDecodeError as exc:
        return f"[Request JSON parse error: {exc}]"
    except OSError as exc:
        return f"[Could not read request: {exc}]"

    from msi_image_render import render_news_image
    result = render_news_image(request_data)

    if not result.get("success"):
        lines = [
            "**News image render failed.**",
            "",
            f"- **Error:** {result.get('error', '<unknown>')}",
        ]
        attempts = result.get("attempts") or []
        if attempts:
            lines.append("- **Attempts:**")
            for attempt in attempts:
                marker = "✓" if attempt.get("succeeded") else "✗"
                code = attempt.get("error_code") or "<ok>"
                lines.append(
                    f"  - {marker} `{attempt.get('provider_id')}` ({code})"
                )
        return "\n".join(lines)

    lines = [
        "**News image rendered.**",
        "",
        f"- **Image asset:** `{result['image_path']}`",
        f"- **Article file:** `{result['article_md_path']}`",
        f"  - frontmatter `image:` field "
        + ("updated" if result.get("article_md_updated")
           else "**not** updated (file does not exist yet — write the "
                "article first, then re-run)"),
        f"- **Provider:** `{result['image_schema']['ai_model']}`",
    ]
    removed = result.get("removed_entities") or []
    if removed:
        lines.append(
            "- **Likeness gate removed:** "
            + ", ".join(f"`{name}`" for name in removed)
        )
    attempts = result.get("attempts") or []
    if len(attempts) > 1:
        lines.append("- **Fallback chain:**")
        for attempt in attempts:
            marker = "✓" if attempt.get("succeeded") else "✗"
            code = attempt.get("error_code") or "ok"
            lines.append(
                f"  - {marker} `{attempt.get('provider_id')}` ({code})"
            )
    lines.append("")
    lines.append(
        "Run `npm run build` in `~/sites/mainstreetindependent/` to "
        "verify the article compiles, then `git push` to deploy."
    )
    return "\n".join(lines)


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python slash_commands.py '<full slash command line>'")
        print("Example: python slash_commands.py '/queue'")
        sys.exit(1)
    print(run_runtime_command(sys.argv[1]))
