"""Phase 3 — Provenance migration

One-time migration pass for Schema rev 5 (2026-05-09): apply
provenance-modifier tags to existing engrams based on `source_side`,
and convert the lone msi-research-typed note to engram.

Mapping rules per Reference — Ora YAML Schema §6.5:
    source_side: ai       → add `ai-derived`     tag (P1, weight 0.9)
    source_side: user     → no change            (P1, weight 1.0)
    no source_side field  → no change            (defaults to user-authored)
    type: msi-research    → type: engram + `source-derived` tag

Idempotent: skips files where the target tag is already present.

Surgical text editing — preserves YAML formatting; does not reformat
the frontmatter. Uses git as the safety net (vault is a git repo).

Usage:
    python3 phase3_provenance_migration.py --dry-run              # default
    python3 phase3_provenance_migration.py --apply                # mutate files
    python3 phase3_provenance_migration.py --apply --sample 10    # apply to N
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import glob
import random


ENGRAMS_DIR = os.path.expanduser("~/Documents/vault/Engrams")

# Match `source_side: ai` (with optional surrounding whitespace) in YAML.
SOURCE_SIDE_AI_RE = re.compile(r"^source_side:\s*ai\s*$", re.MULTILINE)

# Match `type: msi-research`.
TYPE_MSI_RE = re.compile(r"^type:\s*msi-research\s*$", re.MULTILINE)

# Match the start of the YAML frontmatter; capture the body so we can
# split the file into [opening ---, frontmatter, closing ---, body].
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def has_tag(frontmatter: str, tag: str) -> bool:
    """Return True if `tag` appears in the tags list (any indent style)."""
    pattern = rf"^[ \t]*-[ \t]+{re.escape(tag)}\s*$"
    return bool(re.search(pattern, frontmatter, re.MULTILINE))


def add_tag_to_frontmatter(frontmatter: str, tag: str) -> str:
    """Insert a new tag at the END of the existing tags: list.

    Handles both flush-left (`- atomic`) and indented (`  - atomic`)
    styles; matches the existing list indentation. If the tags: list
    is empty (or absent), inserts a new tag entry directly after the
    `tags:` line.

    No-op if the tag is already present.
    """
    if has_tag(frontmatter, tag):
        return frontmatter

    # Find the tags: line and the contiguous `- ` lines after it.
    lines = frontmatter.split("\n")
    tags_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^tags:\s*$", line):
            tags_idx = i
            break
        # tags: with inline list (rare) — skip; we only handle block form.
        if re.match(r"^tags:\s*\[", line):
            return frontmatter  # don't try to mutate inline-list form

    if tags_idx is None:
        return frontmatter  # no tags: field — leave alone

    # Find the end of the tags list — first line that doesn't match `^[ \t]*-`.
    end_idx = tags_idx + 1
    indent = ""
    while end_idx < len(lines):
        m = re.match(r"^([ \t]*)-[ \t]+", lines[end_idx])
        if not m:
            break
        if not indent:
            indent = m.group(1)
        end_idx += 1

    # Insert the new tag entry. If the list was empty (no `- ` lines),
    # use flush-left dash by default (the dominant convention in this vault).
    new_line = f"{indent}- {tag}"
    lines.insert(end_idx, new_line)
    return "\n".join(lines)


def convert_msi_to_engram(frontmatter: str) -> str:
    """Replace `type: msi-research` with `type: engram` (preserves whitespace)."""
    return TYPE_MSI_RE.sub("type: engram", frontmatter)


def process_file(path: str) -> dict:
    """Return a dict describing what change (if any) would be applied.

    Keys:
        action: 'ai-tag' | 'msi-convert' | 'no-change' | 'parse-error'
        was_msi: bool — file had type: msi-research
        was_ai:  bool — file had source_side: ai
        already_tagged: bool — already has the target tag (idempotent skip)
        new_content: str — only when there's a change to apply
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"action": "parse-error", "error": str(e)}

    m = FRONTMATTER_RE.match(content)
    if not m:
        return {"action": "no-change", "reason": "no frontmatter"}

    frontmatter, body = m.group(1), m.group(2)
    new_frontmatter = frontmatter
    actions = []

    # Path A: msi-research → engram + source-derived tag
    if TYPE_MSI_RE.search(frontmatter):
        new_frontmatter = convert_msi_to_engram(new_frontmatter)
        if not has_tag(new_frontmatter, "source-derived"):
            new_frontmatter = add_tag_to_frontmatter(new_frontmatter, "source-derived")
        actions.append("msi-convert")

    # Path B: source_side: ai → add ai-derived tag
    if SOURCE_SIDE_AI_RE.search(new_frontmatter):
        if not has_tag(new_frontmatter, "ai-derived"):
            new_frontmatter = add_tag_to_frontmatter(new_frontmatter, "ai-derived")
            actions.append("ai-tag")
        else:
            actions.append("ai-already-tagged")

    if new_frontmatter == frontmatter:
        return {"action": "no-change", "reason": "no signal or already tagged"}

    new_content = f"---\n{new_frontmatter}\n---\n{body}"
    return {
        "action": "+".join(actions) if actions else "no-change",
        "new_content": new_content,
        "old_frontmatter": frontmatter,
        "new_frontmatter": new_frontmatter,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually write changes (default: dry-run)")
    ap.add_argument("--sample", type=int, default=0,
                    help="Process only N random files (debugging)")
    ap.add_argument("--show-diff", type=int, default=5,
                    help="Show frontmatter diff for first N changed files (default: 5)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(ENGRAMS_DIR, "*.md")))
    print(f"Total Engrams: {len(files)}")

    if args.sample > 0:
        random.seed(42)
        files = random.sample(files, min(args.sample, len(files)))
        print(f"Sampling: {len(files)}")

    stats = {
        "ai-tag": 0,
        "msi-convert+source-derived": 0,
        "msi-convert+ai-tag+ai-already-tagged": 0,  # defensive
        "no-change": 0,
        "parse-error": 0,
    }

    diff_shown = 0

    for i, path in enumerate(files):
        result = process_file(path)
        action = result.get("action", "unknown")

        # Normalize compound actions for stats
        if action == "msi-convert":
            stats_key = "msi-convert+source-derived"
        elif action == "msi-convert+ai-tag":
            stats_key = "msi-convert+source-derived"
        elif action == "ai-tag":
            stats_key = "ai-tag"
        elif action == "ai-already-tagged":
            stats_key = "no-change"
        elif "parse-error" in action:
            stats_key = "parse-error"
        else:
            stats_key = "no-change"

        stats[stats_key] = stats.get(stats_key, 0) + 1

        # Show first N diffs for visual confirmation
        if (action != "no-change" and "parse-error" not in action
                and diff_shown < args.show_diff):
            print(f"\n--- {os.path.basename(path)[:60]} [{action}] ---")
            print("OLD:")
            for line in result["old_frontmatter"].split("\n")[:30]:
                print(f"  {line}")
            print("NEW:")
            for line in result["new_frontmatter"].split("\n")[:30]:
                print(f"  {line}")
            diff_shown += 1

        # Apply if requested
        if args.apply and "new_content" in result:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(result["new_content"])
            except Exception as e:
                stats["parse-error"] = stats.get("parse-error", 0) + 1
                print(f"WRITE ERROR on {path}: {e}", file=sys.stderr)

        if (i + 1) % 10000 == 0:
            print(f"  ... {i+1}/{len(files)} processed")

    print("\n=== Summary ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:30} {v:>8}")
    print(f"  {'total':30} {len(files):>8}")
    print()
    if not args.apply:
        print("DRY RUN — no files modified. Re-run with --apply to write changes.")
    else:
        print("APPLIED. Vault is in git; `git diff` shows changes for review.")


if __name__ == "__main__":
    main()
