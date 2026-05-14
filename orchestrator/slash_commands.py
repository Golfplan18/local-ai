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

  /render-missing-article-images [--dry-run] [--include-drafts]
      Auto-trigger: scan the MSI Astro src/content/articles/ directory,
      derive an image request from each article's frontmatter, and run
      render_news_image against any article missing an image: field.
      Skips drafts by default. Use --dry-run to preview before spending.

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


VAULT_DIR = os.path.expanduser("~/Documents/vault/")
ORA_DIR = os.path.expanduser("~/ora/")
DEFAULT_INSTANCE_DIR = os.path.join(VAULT_DIR, "Corpus Instances")
DEFAULT_OUTPUT_DIR = os.path.join(VAULT_DIR, "Outputs")

KNOWN_COMMANDS = {"/instance", "/validate", "/render", "/queue", "/approve",
                  "/deny", "/cleaning", "/news",
                  "/hector-render", "/news-image-render",
                  "/render-missing-article-images",
                  "/render-figure",
                  "/render-article-figures"}


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
        "/render-missing-article-images": _cmd_render_missing_article_images,
        "/render-figure": _cmd_render_figure,
        "/render-article-figures": _cmd_render_article_figures,
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


# ---------- /render-missing-article-images — batch sweep ----------


def _cmd_render_missing_article_images(args: list[str]) -> str:
    """Scan the MSI Astro articles dir for articles missing an image:
    frontmatter field and render one through render_news_image each.

    The auto-trigger that closes the "publisher generates article →
    image appears" loop. Supports two flags:
      --dry-run         Report what would render without spending Buzz.
      --include-drafts  Also process articles with draft: true (default
                        is to skip drafts).

    No path argument is accepted in v1 — the articles dir is hard-coded
    to ``~/sites/mainstreetindependent/src/content/articles/`` (the
    ``ASTRO_ARTICLES_DIR`` in msi_image_render.py). If the publisher
    moves the Astro repo, both the renderer and this sweeper need the
    config change together.
    """
    dry_run = "--dry-run" in args
    include_drafts = "--include-drafts" in args

    from article_image_sweeper import sweep_once
    result = sweep_once(dry_run=dry_run, include_drafts=include_drafts)

    lines = [
        "**News article image sweep "
        + ("(dry run)" if dry_run else "complete") + ".**",
        "",
        f"- **Scanned:** {result.scanned} article(s)",
        f"- **Skipped (already has image):** {result.skipped_has_image}",
        f"- **Skipped (drafts):** {result.skipped_draft}"
        + ("" if not include_drafts else " (processed because --include-drafts)"),
        f"- **Skipped (parse error):** {result.skipped_parse_error}",
        f"- **Rendered:** {len(result.rendered)}",
        f"- **Failed:** {len(result.failed)}",
    ]
    if result.rendered:
        lines.append("")
        lines.append("**Rendered articles:**")
        for r in result.rendered:
            if r.get("dry_run"):
                lines.append(f"- 🔵 `{r['slug']}` (dry run — would render)")
            else:
                provider = r.get("provider", "<unknown>")
                attempts = r.get("attempts") or []
                provider_note = f"via `{provider}`"
                if len(attempts) > 1:
                    chain_summary = " → ".join(
                        ("✓" if a.get("succeeded") else "✗")
                        + a.get("provider_id", "?")
                        for a in attempts
                    )
                    provider_note += f" (chain: {chain_summary})"
                md_note = (
                    "md updated"
                    if r.get("article_md_updated") else "md not updated"
                )
                lines.append(f"- ✅ `{r['slug']}` — {provider_note} ({md_note})")
    if result.failed:
        lines.append("")
        lines.append("**Failed articles:**")
        for f_ in result.failed:
            lines.append(f"- ❌ `{f_['slug']}`: {f_['error']}")
    if (len(result.rendered) > 0 and not dry_run) or result.failed:
        lines.append("")
        lines.append(
            "Run `npm run build` in `~/sites/mainstreetindependent/` to "
            "verify the articles compile, then `git push` to deploy."
        )
    return "\n".join(lines)


# ---------- /render-figure ----------

def _cmd_render_figure(args: list[str]) -> str:
    """Render a single FRED chart as SVG via the Phase 4 chart-emitter.

    Usage:  /render-figure <SERIES_ID> [transformation] [--from YYYY-MM-DD]
                            [--to YYYY-MM-DD] [--article <slug>]
                            [--title "Custom title"]
                            [--caption "Custom caption"]

    Examples:
      /render-figure UNRATE
      /render-figure UNRATE yoy_pct --from 2020-01-01
      /render-figure GDPC1 raw --article 2026-05-13-jobs-report
    """
    if not args:
        return (
            "**Usage:** `/render-figure <SERIES_ID> [transformation] "
            "[--from YYYY-MM-DD] [--to YYYY-MM-DD] [--article <slug>] "
            "[--title \"...\"] [--caption \"...\"]`\n\n"
            "Renders a chart for the given FRED series ID via the data-viz "
            "pipeline. Transformations: `raw` (default), `yoy_pct`, "
            "`first_diff`, `ytd`. SVG is written to "
            "`~/sites/mainstreetindependent/public/figures/` (or a "
            "subdirectory keyed by `--article` slug). Returns the SVG path, "
            "the URL, the source attribution, and the figureSchema dict "
            "ready for Astro frontmatter.\n\n"
            "Example: `/render-figure UNRATE yoy_pct --from 2020-01-01`"
        )

    series_id = args[0]
    transformation = "raw"
    start_date = None
    end_date = None
    article_slug = None
    title = None
    caption = None

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--from" and i + 1 < len(args):
            start_date = args[i + 1]
            i += 2
        elif a == "--to" and i + 1 < len(args):
            end_date = args[i + 1]
            i += 2
        elif a == "--article" and i + 1 < len(args):
            article_slug = args[i + 1]
            i += 2
        elif a == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif a == "--caption" and i + 1 < len(args):
            caption = args[i + 1]
            i += 2
        elif not a.startswith("--") and i == 1:
            transformation = a
            i += 1
        else:
            return f"[/render-figure: unknown or malformed arg `{a}`]"

    try:
        # Lazy import — keeps the slash command module light when not used
        from data_viz_render import (
            FigureRequest, render_figure,
        )
        from integrations.fred_api import SeriesQuery
    except ImportError:
        from orchestrator.data_viz_render import (
            FigureRequest, render_figure,
        )
        from orchestrator.integrations.fred_api import SeriesQuery

    request = FigureRequest(
        series_query=SeriesQuery(
            series_id=series_id,
            observation_start=start_date,
            observation_end=end_date,
        ),
        chart_type="timeseries",
        transformation=transformation,
        title=title,
        caption=caption,
        article_slug=article_slug,
    )

    result = render_figure(request)
    if not result.success:
        return (
            f"[/render-figure FAILED — {result.error_code}]\n\n"
            f"{result.error_message}"
        )

    fs = result.figure_schema
    return (
        f"**Figure rendered.**\n\n"
        f"- **Series:** `{series_id}` ({transformation})\n"
        f"- **SVG path:** `{result.svg_path}`\n"
        f"- **URL:** `{result.url}`\n"
        f"- **Window:** {fs['data_window']}\n"
        f"- **Attribution:** {result.attribution}\n"
        f"- **Alt:** {fs['alt']}\n"
        f"- **Caption:** {fs['caption']}\n"
    )


# ---------- /render-article-figures ----------

def _cmd_render_article_figures(args: list[str]) -> str:
    """Phase 3 — run the article-classifier on a published article and
    render every accepted data-viz opportunity as an SVG, populating
    the article's `figures` frontmatter field.

    Usage: /render-article-figures <article_path or slug> [--dry-run] [--patch]

    The article path can be:
      - An absolute path to the article .md
      - A relative path under the Astro repo's articles or columns dir
      - A slug; the command searches articles/ and columns/ for matches

    --dry-run runs the classifier and prints the analysis without
    rendering figures. Useful for inspecting classifier judgment
    before committing model + render compute time.

    --patch (after a successful render) writes the resulting figureSchema
    list back into the article's YAML frontmatter as the `figures` array.
    Existing frontmatter is preserved; an existing `figures` key is
    replaced. Mutually exclusive with --dry-run (a dry run produces
    nothing to patch).
    """
    if not args:
        return (
            "**Usage:** `/render-article-figures <article_path or slug> "
            "[--dry-run] [--patch]`\n\n"
            "Runs the Phase 3 article-classifier on a published article. "
            "For each accepted data-viz opportunity, invokes the chart "
            "emitter to produce an SVG (Phase 4). Returns the figureSchema "
            "list and a per-opportunity result log.\n\n"
            "If the article is not economic (geopolitics, criminal justice, "
            "etc.), returns success with an empty figures list — that's the "
            "editorially-correct behavior, not a failure.\n\n"
            "Pass `--patch` to write the resulting `figures: [...]` array "
            "back into the article's YAML frontmatter (existing fields "
            "preserved; an existing `figures` key is replaced).\n\n"
            "Example: `/render-article-figures 2026-05-11-iran-rejects-us-proposal-day-72`"
        )

    arg = args[0]
    dry_run = "--dry-run" in args
    patch = "--patch" in args

    # Resolve article path
    article_path = _resolve_article_path(arg)
    if article_path is None:
        return (
            f"[Article not found: `{arg}`. Tried absolute path; "
            f"~/sites/mainstreetindependent/src/content/articles/; "
            f"~/sites/mainstreetindependent/src/content/columns/.]"
        )

    # Lazy-load the module
    try:
        from article_data_viz import (
            parse_article_file, render_figures_for_article,
            analyze_article_for_data_viz,
        )
    except ImportError:
        from orchestrator.article_data_viz import (
            parse_article_file, render_figures_for_article,
            analyze_article_for_data_viz,
        )
    try:
        from boot import call_model, load_endpoints, get_slot_endpoint
    except ImportError:
        return (
            "[Cannot import boot.call_model — run from a context where "
            "~/ora is on the Python path.]"
        )

    article = parse_article_file(article_path)
    if not article:
        return f"[Could not parse article frontmatter from `{article_path}`]"

    config = load_endpoints()
    endpoint = get_slot_endpoint(config, "sidebar")

    # Article slug from the filename
    article_slug = os.path.basename(article_path).rsplit(".", 1)[0]

    if dry_run:
        analysis = analyze_article_for_data_viz(
            article, call_fn=call_model, endpoint=endpoint,
        )
        if analysis.error:
            return f"[Classifier error: {analysis.error}]"
        lines = [
            f"**Article:** `{article_slug}`",
            f"**Headline:** {article.get('headline', '(none)')}",
            f"**Warrants charts:** {analysis.warrants_charts}",
            f"**Opportunities ({len(analysis.opportunities)}):**",
        ]
        for o in analysis.opportunities:
            lines.append(
                f"- [{o.priority}] `{o.series_id}` ({o.transformation}) — "
                f"{o.narrative_role}"
            )
            if o.justification:
                lines.append(f"  - _{o.justification}_")
        if not analysis.opportunities:
            lines.append("- _(none — classifier judges no charts warranted)_")
        lines.append("")
        lines.append("_Dry-run mode; no figures rendered._")
        return "\n".join(lines)

    # Full render
    result = render_figures_for_article(
        article, call_fn=call_model, endpoint=endpoint,
        article_slug=article_slug,
    )

    lines = [
        f"**Article:** `{article_slug}`",
        f"**Headline:** {article.get('headline', '(none)')}",
        f"**Classifier verdict:** {'charts warranted' if result.analysis and result.analysis.warrants_charts else 'no charts warranted'}",
    ]

    if result.analysis and result.analysis.opportunities:
        lines.append(f"**Opportunities identified:** {len(result.analysis.opportunities)}")
    lines.append(f"**Figures rendered successfully:** {len(result.figures)}")

    # Surface per-figure failures with envelope debug logs when any failed.
    # Map: index-in-figure_results -> debug-log path (or None).
    failure_debug_paths: dict[int, str] = {}
    if result.figure_results:
        try:
            failure_debug_paths = _write_failure_debug_logs(
                article_slug, result.figure_results,
            )
        except Exception:  # pragma: no cover — debug logging must not break flow
            failure_debug_paths = {}

    if result.figure_results:
        lines.append("")
        lines.append("**Per-figure detail:**")
        for idx, fr in enumerate(result.figure_results):
            if fr.success:
                lines.append(
                    f"- ✅ `{fr.figure_schema.get('source', '?')}` → "
                    f"`{fr.url}`"
                )
            else:
                debug_path = failure_debug_paths.get(idx)
                debug_note = (
                    f" — debug: `{debug_path}`" if debug_path else ""
                )
                lines.append(
                    f"- ❌ failed [{fr.error_code}]: {fr.error_message}"
                    f"{debug_note}"
                )

    if not result.success and result.error:
        lines.append("")
        lines.append(f"_{result.error}_")

    # --patch: write figures back into the article frontmatter.
    # Only patches when the render succeeded AND produced at least one
    # figure. A run that correctly returns zero figures (non-economic
    # article) does not mutate the file — there's nothing to write.
    if patch:
        if not result.success:
            lines.append("")
            lines.append("_--patch skipped: render did not succeed._")
        elif not result.figures:
            lines.append("")
            lines.append(
                "_--patch skipped: no figures to write "
                "(classifier judged none warranted)._"
            )
        else:
            try:
                _patch_article_frontmatter_figures(article_path, result.figures)
                lines.append("")
                lines.append(
                    f"**Frontmatter patched:** `{article_path}` "
                    f"→ `figures: [...]` ({len(result.figures)} entries)"
                )
            except Exception as exc:
                lines.append("")
                lines.append(f"_--patch failed (frontmatter): {exc}_")
            # Auto-embed inline `<figure>` blocks in the body. MSI is
            # a zero-manual-labor publication; frontmatter alone leaves
            # the publisher to hand-place charts in the body, which is
            # the manual-labor step we explicitly eliminate here.
            try:
                placed = _patch_article_body_with_figures(
                    article_path, result.figures,
                )
                lines.append(
                    f"**Body patched:** {placed} `<figure>` block(s) embedded "
                    f"inline at anchor paragraphs"
                )
            except Exception as exc:
                lines.append(f"_--patch failed (body): {exc}_")

    # Fact-check article body values against FRED — runs regardless
    # of --patch since the discrepancies are informational. Writes a
    # JSON log under ~/ora/data/data-viz-debug/<slug>/fact-check.json;
    # surfaces a summary line in the response.
    try:
        fact_check_summary = _run_fact_check_and_log(
            article, result, article_slug,
        )
        if fact_check_summary:
            lines.append("")
            lines.append(fact_check_summary)
    except Exception as exc:  # pragma: no cover — must never block render
        lines.append(f"_fact-check pass failed: {exc}_")

    return "\n".join(lines)


def _run_fact_check_and_log(article: dict,
                             result,
                             article_slug: str) -> str:
    """Run the fact-check against FRED for the article's picked
    indicators and write a JSON log to the data-viz debug directory.

    Returns a one-line markdown summary for the slash command output.
    Never raises — fact-check is informational, must not block render.
    """
    try:
        from article_data_viz import fact_check_article_against_fred
    except ImportError:
        from orchestrator.article_data_viz import fact_check_article_against_fred

    analysis = result.analysis if result and getattr(result, "analysis", None) else None
    scored = getattr(analysis, "picked_scored_indicators", None) if analysis else None
    if not scored:
        return ""  # nothing to check — classifier mode or no picks

    fc_results = fact_check_article_against_fred(article, scored)
    if not fc_results:
        return ""

    # Persist log
    try:
        from dataclasses import asdict as _asdict
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        target_dir = os.path.join(
            _DATA_VIZ_DEBUG_DIR,
            article_slug or "_unknown_article",
        )
        os.makedirs(target_dir, exist_ok=True)
        log_path = os.path.join(target_dir, "fact-check.json")
        payload = {
            "logged_at_utc": _dt.now(_tz.utc).isoformat(timespec="seconds"),
            "article_slug": article_slug,
            "tolerance_pp": 0.5,
            "results": [_asdict(r) for r in fc_results],
        }
        with open(log_path, "w", encoding="utf-8") as f:
            _json.dump(payload, f, indent=2)
    except Exception:  # pragma: no cover — log-write best-effort
        log_path = None

    # Summary counts
    failures = [r for r in fc_results
                if r.discrepancy_pp is not None and not r.within_tolerance]
    skipped = [r for r in fc_results if r.discrepancy_pp is None]
    checked = [r for r in fc_results
               if r.discrepancy_pp is not None and r.within_tolerance]

    lines = [
        f"**Fact-check vs FRED:** {len(checked)} pass, "
        f"{len(failures)} discrepancy, {len(skipped)} skipped"
    ]
    if log_path:
        lines.append(f"_Log: `{log_path}`_")
    for r in failures[:4]:
        lines.append(
            f"- ⚠️  `{r.series_id}` claim `{r.claim_id}`: "
            f"article {r.article_value}% vs FRED {r.fred_value:.2f}% "
            f"(Δ {r.discrepancy_pp:.2f}pp)"
        )
    return "\n".join(lines)


_DATA_VIZ_DEBUG_DIR = os.path.expanduser("~/ora/data/data-viz-debug")


def _write_failure_debug_logs(article_slug: str,
                              figure_results: list) -> dict[int, str]:
    """Persist a JSON debug record for every failed FigureResult.

    Each failed figure gets a single JSON file under
    ``~/ora/data/data-viz-debug/<article_slug>/<series_id>-<transformation>.json``
    (filename derived from the envelope when available, else from the
    failure index). Records carry the error code + message, the envelope
    JSON if the failure happened post-envelope-build (so the visual
    compiler input can be re-played manually), and a UTC timestamp.

    Returns a mapping: index-in-figure_results -> absolute debug path.
    Successful figures and figures with no envelope-or-error context are
    omitted from the returned map.

    Failure modes:
      - Permission / disk failures during write: that single record is
        skipped (other records still attempted) and the index is omitted
        from the returned map. Caller treats absence as "no debug log".
    """
    out: dict[int, str] = {}

    failures = [
        (idx, fr) for idx, fr in enumerate(figure_results) if not fr.success
    ]
    if not failures:
        return out

    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    article_dir_name = article_slug or "_unkown_article"
    target_dir = os.path.join(_DATA_VIZ_DEBUG_DIR, article_dir_name)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        return out

    used_names: set[str] = set()
    for idx, fr in failures:
        # Derive a stable filename from the envelope id or failure index.
        envelope = getattr(fr, "envelope", None) or {}
        env_id = (envelope.get("id") if isinstance(envelope, dict) else None)
        if env_id:
            base_name = str(env_id)
        else:
            base_name = f"failure-{idx:02d}"
        # Avoid collisions if two failures share an envelope id
        candidate = base_name
        suffix = 1
        while candidate in used_names:
            suffix += 1
            candidate = f"{base_name}-{suffix}"
        used_names.add(candidate)
        filename = f"{candidate}.json"
        path = os.path.join(target_dir, filename)

        record = {
            "logged_at_utc": _dt.now(_tz.utc).isoformat(timespec="seconds"),
            "article_slug": article_slug,
            "figure_index": idx,
            "error_code": getattr(fr, "error_code", "") or "",
            "error_message": getattr(fr, "error_message", "") or "",
            "envelope": envelope if isinstance(envelope, dict) else None,
            "figure_schema": getattr(fr, "figure_schema", None) or None,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(record, f, indent=2, default=str)
            out[idx] = path
        except OSError:
            # Single-record failure shouldn't cascade
            continue

    return out


_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def _figure_footnote_id(figure_url: str) -> str:
    """Mirror ArticleLayout.astro's figureFootnoteId: derive a stable
    footnote anchor id from the figure's URL filename. Example:
    `/figures/<slug>/fig-cpiaucsl-yoy_pct.svg` → `fig-src-cpiaucsl-yoy_pct`."""
    base = (figure_url or "").split("/")[-1]
    stem = re.sub(r"\.svg$", "", base, flags=re.IGNORECASE)
    stem = re.sub(r"^fig-", "", stem)
    return f"fig-src-{stem}"


def _series_id_from_figure_url(figure_url: str) -> str:
    """Extract the FRED series_id from a figure URL.
    Example: `/figures/<slug>/fig-cpiaucsl-yoy_pct.svg` → `CPIAUCSL`."""
    base = (figure_url or "").split("/")[-1]
    stem = re.sub(r"\.svg$", "", base, flags=re.IGNORECASE)
    stem = re.sub(r"^fig-", "", stem)
    # Series id is whatever precedes the trailing -<transformation>.
    # Transformations are a known closed set; strip those suffixes.
    for suffix in ("-yoy_pct", "-first_diff", "-ytd", "-raw"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.upper().replace("-", "")


def _short_indicator_name(figure: dict) -> str:
    """Resolve a clean short name for inline-caption use.

    Looks up INDICATOR_CATALOG by series_id (parsed from the figure
    URL) and returns the catalog `name` with parenthetical stripped
    (e.g., "Consumer Price Index (all urban consumers)" → "Consumer
    Price Index"). Falls back to parsing the figureSchema's `source`
    field when the catalog lookup fails.
    """
    try:
        from article_data_viz import INDICATOR_CATALOG
    except ImportError:
        from orchestrator.article_data_viz import INDICATOR_CATALOG
    sid = _series_id_from_figure_url(figure.get("url", ""))
    for entry in INDICATOR_CATALOG:
        if entry.get("series_id") == sid:
            name = entry.get("name", "")
            return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    # Fallback: parse "FRED, <name> (<series_id>)"
    source = figure.get("source", "")
    m = re.match(r"FRED,\s+(.+?)\s+\([^)]+\)\s*$", source)
    if m:
        n = m.group(1).strip()
        # Trim disambiguating suffix after ": "
        return n.split(":")[0].strip()
    return source or sid


_TRANSFORMATION_INLINE_LABELS: dict[str, str] = {
    "raw": "",
    "yoy_pct": "year-over-year",
    "first_diff": "month-over-month",
    "ytd": "year-to-date",
    "level_vs_average": "vs. historical average",
    "cumulative": "cumulative",
    "other": "",
}


def _short_date_range(data_window: str) -> str:
    """Convert "2022-01-01 to 2026-04-01" → "2022–2026". Robust to
    weekly windows ("2021-01-07 to 2026-05-07") and missing strings.
    Returns "" when the format isn't recognised."""
    if not data_window:
        return ""
    m = re.match(r"\s*(\d{4})-\d{2}-\d{2}\s+to\s+(\d{4})-\d{2}-\d{2}\s*$",
                 data_window)
    if not m:
        return data_window  # use as-is if unparseable
    a, b = m.group(1), m.group(2)
    if a == b:
        return a
    return f"{a}–{b}"  # en-dash


def _build_inline_figure_html(figure: dict,
                              footnote_num: int,
                              float_side: str) -> str:
    """Produce the `<figure>` block to embed inline in the article body.

    Wrapped with start/end markers so re-render can strip cleanly:
        <!-- ora-figure-start: <series_id> --> ... <!-- ora-figure-end -->
    """
    url = figure.get("url", "")
    alt = figure.get("alt", "")
    short_name = _short_indicator_name(figure)
    transformation = figure.get("transformation", "raw")
    transformation_label = _TRANSFORMATION_INLINE_LABELS.get(transformation, "")
    date_range = _short_date_range(figure.get("data_window", ""))

    parts = [short_name]
    if transformation_label:
        parts.append(transformation_label)
    if date_range:
        parts.append(date_range)
    caption_lead = ", ".join(parts)

    superscript = (
        _SUPERSCRIPTS[footnote_num] if 0 <= footnote_num < len(_SUPERSCRIPTS)
        else f"({footnote_num})"
    )
    footnote_id = _figure_footnote_id(url)
    series_id = _series_id_from_figure_url(url)

    float_class = (
        "article-figure--float-right" if float_side == "right"
        else "article-figure--float-left"
    )

    return (
        f"<!-- ora-figure-start: {series_id} -->\n"
        f'<figure class="article-figure {float_class}">\n'
        f'  <img src="{url}" alt="{alt}" loading="lazy" />\n'
        f'  <figcaption>{caption_lead}. '
        f'<a href="#{footnote_id}">{superscript}</a></figcaption>\n'
        f"</figure>\n"
        f"<!-- ora-figure-end -->"
    )


_FIGURE_BLOCK_RE = re.compile(
    # Auto-inserted (marker-wrapped) blocks.
    r"<!--\s*ora-figure-start[^>]*-->\s*"
    r"<figure[^>]*class=\"article-figure[^\"]*\".*?</figure>\s*"
    r"<!--\s*ora-figure-end\s*-->\s*",
    re.DOTALL,
)
_BARE_FIGURE_BLOCK_RE = re.compile(
    # Any article-figure block, with or without markers — strips
    # legacy manual inserts during the transition to fully-automated
    # placement.
    r"<figure[^>]*class=\"article-figure[^\"]*\".*?</figure>\s*",
    re.DOTALL,
)


def _strip_existing_figures(body: str) -> str:
    """Remove all article-figure blocks (auto and legacy-manual)
    along with their surrounding blank lines."""
    body = _FIGURE_BLOCK_RE.sub("", body)
    body = _BARE_FIGURE_BLOCK_RE.sub("", body)
    # Collapse triple-or-more newlines left behind by strips.
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body


def _split_body_into_blocks(body: str) -> list[str]:
    """Split body markdown into blocks (paragraphs / headings) using
    blank-line boundaries. Preserves block order; drops empty entries."""
    blocks = re.split(r"\n\s*\n", body)
    return [b.rstrip() for b in blocks if b.strip()]


def _is_paragraph(block: str) -> bool:
    """True if the block is a body paragraph (not a heading or HTML)."""
    stripped = block.lstrip()
    if stripped.startswith("#"):
        return False
    if stripped.startswith("<"):
        return False
    return bool(stripped)


def _find_anchor_block(blocks: list[str],
                       figure: dict,
                       claimed: set[int]) -> int:
    """Find the index of the best paragraph block to anchor this figure.

    Strategy:
      1. Phrase match — try diagnostic phrases (catalog name + n-grams)
         against each unclaimed paragraph; return the first hit.
      2. Section-fallback — pick the first unclaimed paragraph that
         hasn't been claimed yet.

    Returns -1 only when there are no unclaimed paragraphs at all
    (defensive — for a normal article + 4 figures we should always
    find a slot).
    """
    try:
        from article_data_viz import INDICATOR_CATALOG, _diagnostic_phrases
    except ImportError:
        from orchestrator.article_data_viz import (
            INDICATOR_CATALOG, _diagnostic_phrases,
        )

    sid = _series_id_from_figure_url(figure.get("url", ""))
    entry = next(
        (e for e in INDICATOR_CATALOG if e.get("series_id") == sid), None,
    )
    phrases: set[str] = set()
    if entry:
        phrases = _diagnostic_phrases(entry)
    # Augment with the short name as a phrase (catches inflected forms).
    short_name = _short_indicator_name(figure).lower()
    if short_name and len(short_name) >= 4:
        phrases.add(short_name)

    # Strategy 1: phrase match (longest phrases first to prefer specific
    # matches over generic ones).
    sorted_phrases = sorted(phrases, key=lambda p: (-len(p), p))
    for phrase in sorted_phrases:
        if not phrase or len(phrase) < 4:
            continue
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b",
                             re.IGNORECASE)
        for i, block in enumerate(blocks):
            if i in claimed or not _is_paragraph(block):
                continue
            if pattern.search(block):
                return i

    # Strategy 2: first unclaimed paragraph.
    for i, block in enumerate(blocks):
        if i in claimed or not _is_paragraph(block):
            continue
        return i

    return -1


def _patch_article_body_with_figures(article_path: str,
                                     figures: list[dict]) -> int:
    """Auto-embed `<figure>` blocks inline in the article body.

    Strips all existing article-figure blocks (auto-inserted and
    legacy-manual) and re-inserts fresh ones at computed anchor
    paragraphs. Each figure is wrapped with start/end marker comments
    so future re-renders can strip cleanly. Float side alternates
    right/left across the picks for visual rhythm.

    Returns the number of figures placed.
    """
    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        raise ValueError(
            f"Article has no YAML frontmatter: {article_path}"
        )
    end_marker = content.find("\n---", 4)
    if end_marker < 0:
        raise ValueError(
            f"Article frontmatter has no closing `---`: {article_path}"
        )
    fm_block = content[: end_marker + len("\n---")]
    body = content[end_marker + len("\n---"):]
    # Ensure body starts with a single newline.
    if body.startswith("\n"):
        body = body[1:]

    body = _strip_existing_figures(body)
    blocks = _split_body_into_blocks(body)

    claimed: set[int] = set()
    inserts_before: dict[int, list[str]] = {}
    placed = 0
    for i, figure in enumerate(figures):
        anchor_idx = _find_anchor_block(blocks, figure, claimed)
        if anchor_idx < 0:
            continue
        claimed.add(anchor_idx)
        float_side = "right" if (placed % 2 == 0) else "left"
        figure_html = _build_inline_figure_html(figure, placed + 1, float_side)
        inserts_before.setdefault(anchor_idx, []).append(figure_html)
        placed += 1

    # Apply inserts in reverse index order so positions don't shift.
    for idx in sorted(inserts_before.keys(), reverse=True):
        for fig_html in reversed(inserts_before[idx]):
            blocks.insert(idx, fig_html)

    new_body = "\n\n".join(blocks) + "\n"
    new_content = f"{fm_block}\n{new_body}"

    # Atomic write — same pattern as the frontmatter patcher.
    import tempfile as _tempfile
    dir_ = os.path.dirname(article_path) or "."
    fd, tmp_path = _tempfile.mkstemp(prefix=".bodypatch.", suffix=".md", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, article_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return placed


def _patch_article_frontmatter_figures(article_path: str,
                                       figures: list[dict]) -> None:
    """Write `figures: [...]` into the article's YAML frontmatter.

    Reads the .md file, splits frontmatter from body using the leading
    `---` markers, parses YAML, sets/replaces the `figures` key, and
    writes the file back. Existing frontmatter fields are preserved.
    Order is preserved as best as PyYAML's round-trip can manage
    (sort_keys=False); multi-line scalars and list ordering of other
    fields are not reordered. The body content is preserved byte-for-byte.

    Raises:
      FileNotFoundError if article_path does not exist
      ValueError if the file has no parseable YAML frontmatter
      ImportError if PyYAML is not available (we rely on it for write)
    """
    import yaml  # PyYAML — required for the dump path

    with open(article_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        raise ValueError(
            f"Article has no YAML frontmatter (no leading `---`): {article_path}"
        )

    # Find end of frontmatter; matches parse_article_file's approach.
    end_marker = content.find("\n---", 4)
    if end_marker < 0:
        raise ValueError(
            f"Article frontmatter has no closing `---`: {article_path}"
        )

    fm_text = content[3:end_marker].strip()
    # Body starts after the closing `---\n` (the find above lands ON the
    # leading `\n` of `\n---`, so move past `\n---` and keep the trailing
    # newline if present).
    body_start = end_marker + len("\n---")
    body = content[body_start:]
    # Normalize: ensure body begins with a single newline so the rebuilt
    # file reads `---\n<body>` cleanly.
    if body.startswith("\n"):
        body = body[1:]

    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ValueError(
            f"Article frontmatter is not a mapping: {article_path}"
        )

    fm["figures"] = figures

    new_fm_text = yaml.dump(
        fm,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=10_000,  # avoid surprise line wrapping inside long strings
    )
    # PyYAML returns a trailing newline after the last value; strip it
    # so the assembled file has exactly one blank line / boundary.
    new_fm_text = new_fm_text.rstrip("\n")

    new_content = f"---\n{new_fm_text}\n---\n{body}"

    # Atomic write: write to a sibling tempfile, fsync, then rename.
    import tempfile as _tempfile
    dir_ = os.path.dirname(article_path) or "."
    fd, tmp_path = _tempfile.mkstemp(
        prefix=".patch.", suffix=".md", dir=dir_,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # best-effort fsync; some filesystems don't support it
        os.replace(tmp_path, article_path)
    except Exception:
        # Clean up the tempfile on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _resolve_article_path(arg: str) -> Optional[str]:
    """Resolve an article path or slug to an absolute file path."""
    expanded = os.path.expanduser(arg)
    if os.path.isabs(expanded) and os.path.isfile(expanded):
        return expanded

    astro_root = os.path.expanduser("~/sites/mainstreetindependent/src/content")
    for subdir in ("articles", "columns"):
        # Direct path (with or without .md)
        for candidate_name in (arg, f"{arg}.md"):
            candidate = os.path.join(astro_root, subdir, candidate_name)
            if os.path.isfile(candidate):
                return candidate
        # Slug match — find any file containing the slug
        search_dir = os.path.join(astro_root, subdir)
        if os.path.isdir(search_dir):
            for f in os.listdir(search_dir):
                if arg in f and f.endswith(".md"):
                    return os.path.join(search_dir, f)

    return None


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python slash_commands.py '<full slash command line>'")
        print("Example: python slash_commands.py '/queue'")
        sys.exit(1)
    print(run_runtime_command(sys.argv[1]))
