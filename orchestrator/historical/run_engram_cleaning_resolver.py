"""Engram Cleaning Framework — resolver phase.

Reads the queue file the user edited with resolution markers, applies
mechanical YAML mutations per resolution, refreshes ChromaDB metadata,
and appends to the resolution log.

See `Framework — Engram Cleaning` (vault canonical) for the full spec.

Idempotency: each resolution is applied exactly once; running twice is
safe (already-archived notes are no-ops; supersedes relationships are
deduplicated by the YAML's UNIQUE constraint pattern).

Usage:
    python3 run_engram_cleaning_resolver.py [--delete-wrong] [--dry-run]

Resolution markers handled:
    [changed-mind:source-supersedes-target]
    [changed-mind:target-supersedes-source]
    [hypocrisy]
    [wrong:source]
    [wrong:target]
    [skip]
    [pending]  — left as-is (skipped this run)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import sqlite3
from datetime import datetime
from typing import Optional

import yaml


VAULT_ROOT = os.path.expanduser("~/Documents/vault")
ENGRAMS_DIR = os.path.join(VAULT_ROOT, "Engrams")
QUEUE_FILE = os.path.join(
    VAULT_ROOT, "Projects", "Ora", "Working — Engram Cleaning Queue.md"
)
LOG_FILE = os.path.join(
    VAULT_ROOT, "Projects", "Ora", "Working — Engram Cleaning Log.md"
)
HYPOCRISY_FILE = os.path.join(
    VAULT_ROOT, "Projects", "Ora", "Working — Engram Cleaning Hypocrisy Review.md"
)

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")
COLLECTION_NAME = "knowledge"

VALID_RESOLUTIONS = {
    "changed-mind:source-supersedes-target",
    "changed-mind:target-supersedes-source",
    "hypocrisy",
    "wrong:source",
    "wrong:target",
    "skip",
}


# ---------------------------------------------------------------------------
# Queue parsing
# ---------------------------------------------------------------------------


# The user-edit canonical line is `**Resolution:** [marker]`. The heading
# marker (`## [pending] ...`) is a visual scan aid only — never read as
# canonical. Pairs are matched by anchoring on Source/Target wikilinks and
# scanning forward to the next Resolution line.
PAIR_RE = re.compile(
    r"- \*\*Source:\*\* \[\[(?P<source_slug>[^\]]+)\]\].*?\n"
    r"\s*\*(?P<source_h1>[^*]+)\*\n"
    r".*?- \*\*Target:\*\* \[\[(?P<target_slug>[^\]]+)\]\].*?\n"
    r"\s*\*(?P<target_h1>[^*]+)\*\n"
    r".*?\*\*Resolution:\*\*\s*\[(?P<resolution>[^\]]+)\]",
    re.DOTALL,
)


def parse_queue(queue_text: str) -> list[dict]:
    """Yield {resolution, source_slug, source_h1, target_slug, target_h1} per pair.

    Canonical resolution marker comes from the `**Resolution:** [marker]` line
    (the user-facing edit point), not from the heading. The heading marker is
    informational only — see the framework spec.
    """
    pairs = []
    for m in PAIR_RE.finditer(queue_text):
        pairs.append({
            "resolution": m.group("resolution").strip(),
            "source_slug": m.group("source_slug").strip(),
            "source_h1": m.group("source_h1").strip(),
            "target_slug": m.group("target_slug").strip(),
            "target_h1": m.group("target_h1").strip(),
        })
    return pairs


_RESOLUTION_LINE_RE = re.compile(r"\*\*Resolution:\*\*\s*\[([^\]]+)\]")


def _rebuild_queue_keeping_pending(queue_text: str) -> str:
    """Rewrite queue text keeping only sections whose Resolution line is [pending].

    The split is on the `## [marker] ` heading boundary; pending status is
    determined from the body's Resolution line, not the heading marker.
    """
    sections = re.split(r"^(## \[[^\]]+\] )", queue_text, flags=re.MULTILINE)
    new_text = sections[0]
    i = 1
    while i < len(sections):
        heading = sections[i]
        body = sections[i + 1] if i + 1 < len(sections) else ""
        m = _RESOLUTION_LINE_RE.search(body)
        marker = m.group(1).strip() if m else "pending"
        if marker == "pending":
            new_text += heading + body
        i += 2
    return new_text


# ---------------------------------------------------------------------------
# YAML mutations (frontmatter-preserving surgical edits)
# ---------------------------------------------------------------------------


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def read_engram(slug: str) -> Optional[tuple[str, str]]:
    """Return (frontmatter, body) for the engram, or None if missing."""
    path = os.path.join(ENGRAMS_DIR, f"{slug}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    m = FRONTMATTER_RE.match(content)
    if not m:
        return None
    return m.group(1), m.group(2)


def write_engram(slug: str, frontmatter: str, body: str):
    path = os.path.join(ENGRAMS_DIR, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{frontmatter}\n---\n{body}")


def has_tag(frontmatter: str, tag: str) -> bool:
    pattern = rf"^[ \t]*-[ \t]+{re.escape(tag)}\s*$"
    return bool(re.search(pattern, frontmatter, re.MULTILINE))


def add_tag(frontmatter: str, tag: str) -> str:
    """Insert a tag at the end of the tags: list (idempotent)."""
    if has_tag(frontmatter, tag):
        return frontmatter
    lines = frontmatter.split("\n")
    tags_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^tags:\s*$", line):
            tags_idx = i
            break
    if tags_idx is None:
        return frontmatter
    end_idx = tags_idx + 1
    indent = ""
    while end_idx < len(lines):
        m = re.match(r"^([ \t]*)-[ \t]+", lines[end_idx])
        if not m:
            break
        if not indent:
            indent = m.group(1)
        end_idx += 1
    lines.insert(end_idx, f"{indent}- {tag}")
    return "\n".join(lines)


def add_supersedes_relationship(frontmatter: str, target_h1: str) -> str:
    """Append a supersedes relationship to the relationships: list (idempotent).

    If the relationships block is missing, creates it before `date created:`.
    """
    # Idempotent: skip if a supersedes edge to this target already exists
    fm_data = yaml.safe_load(frontmatter) or {}
    existing = fm_data.get("relationships") or []
    for rel in existing:
        if (isinstance(rel, dict)
                and rel.get("type") == "supersedes"
                and rel.get("target") == target_h1):
            return frontmatter

    new_entry_lines = [
        "- type: supersedes",
        f"  target: {yaml_escape(target_h1)}",
        "  confidence: high",
    ]

    lines = frontmatter.split("\n")

    # If relationships: block exists, append before next non-list line
    rel_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^relationships:\s*$", line):
            rel_idx = i
            break

    if rel_idx is not None:
        # Find end of relationships list (first line that's not a list item)
        end_idx = rel_idx + 1
        while end_idx < len(lines):
            if (lines[end_idx].startswith("- ")
                    or lines[end_idx].startswith("  ")):
                end_idx += 1
            else:
                break
        # Insert at end of relationships block
        for offset, new_line in enumerate(new_entry_lines):
            lines.insert(end_idx + offset, new_line)
    else:
        # No relationships block — create one before `date created:` (if present)
        # or at the end of frontmatter.
        insert_idx = len(lines)
        for i, line in enumerate(lines):
            if re.match(r"^date created:", line):
                insert_idx = i
                break
        new_block = ["relationships:"] + new_entry_lines
        for offset, new_line in enumerate(new_block):
            lines.insert(insert_idx + offset, new_line)

    return "\n".join(lines)


def yaml_escape(s: str) -> str:
    """Escape a string for safe YAML inline emission."""
    if any(c in s for c in ":#'\"[]{}|*&!%@,\\"):
        # Quote and escape internal quotes
        return "'" + s.replace("'", "''") + "'"
    return s


# ---------------------------------------------------------------------------
# Resolution dispatch
# ---------------------------------------------------------------------------


def apply_changed_mind(survivor_slug: str, archived_slug: str,
                       archived_h1: str, dry_run: bool) -> dict:
    """survivor's frontmatter gets a supersedes→archived relationship;
    archived's frontmatter gets an archived tag.
    """
    out = {"mutated_files": [], "errors": []}

    survivor = read_engram(survivor_slug)
    if survivor is None:
        out["errors"].append(f"survivor not found: {survivor_slug}")
        return out
    archived = read_engram(archived_slug)
    if archived is None:
        out["errors"].append(f"archived note not found: {archived_slug}")
        return out

    s_fm, s_body = survivor
    a_fm, a_body = archived

    new_s_fm = add_supersedes_relationship(s_fm, archived_h1)
    new_a_fm = add_tag(a_fm, "archived")

    if not dry_run:
        if new_s_fm != s_fm:
            write_engram(survivor_slug, new_s_fm, s_body)
            out["mutated_files"].append(f"{survivor_slug}.md")
        if new_a_fm != a_fm:
            write_engram(archived_slug, new_a_fm, a_body)
            out["mutated_files"].append(f"{archived_slug}.md")
    else:
        if new_s_fm != s_fm:
            out["mutated_files"].append(f"[dry-run] {survivor_slug}.md (+supersedes)")
        if new_a_fm != a_fm:
            out["mutated_files"].append(f"[dry-run] {archived_slug}.md (+archived tag)")

    return out


def apply_wrong(slug: str, dry_run: bool) -> dict:
    """Add archived tag to the named engram."""
    out = {"mutated_files": [], "errors": []}
    target = read_engram(slug)
    if target is None:
        out["errors"].append(f"not found: {slug}")
        return out
    fm, body = target
    new_fm = add_tag(fm, "archived")
    if not dry_run:
        if new_fm != fm:
            write_engram(slug, new_fm, body)
            out["mutated_files"].append(f"{slug}.md")
    else:
        if new_fm != fm:
            out["mutated_files"].append(f"[dry-run] {slug}.md (+archived tag)")
    return out


def apply_hypocrisy(pair: dict, dry_run: bool) -> dict:
    """Append the pair to the Hypocrisy Review file. No engram mutation."""
    out = {"mutated_files": [], "errors": []}
    if dry_run:
        out["mutated_files"].append(f"[dry-run] append to {os.path.basename(HYPOCRISY_FILE)}")
        return out

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {timestamp} — flagged for review\n\n"
        f"- **Source:** [[{pair['source_slug']}]]\n"
        f"  *{pair['source_h1']}*\n"
        f"- **Target:** [[{pair['target_slug']}]]\n"
        f"  *{pair['target_h1']}*\n\n"
        f"---\n"
    )

    if not os.path.exists(HYPOCRISY_FILE):
        header = (
            "---\n"
            "nexus:\n  - ora\n"
            "type: working\n"
            "tags:\n  - engram-cleaning\n  - hypocrisy-review\n"
            f"date created: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"date modified: {datetime.now().strftime('%Y-%m-%d')}\n"
            "---\n\n"
            "# Engram Cleaning — Hypocrisy / Motivated-Reasoning Review\n\n"
            "*Pairs the user flagged as reflecting genuine tension or motivated reasoning. "
            "No automatic mutations applied — these are for the user's reflection. "
            "Resolve at your own pace by editing the relevant engrams directly or "
            "re-running detection after the underlying thinking has clarified.*\n"
        )
        with open(HYPOCRISY_FILE, "w", encoding="utf-8") as f:
            f.write(header + entry)
    else:
        with open(HYPOCRISY_FILE, "a", encoding="utf-8") as f:
            f.write(entry)

    out["mutated_files"].append(os.path.basename(HYPOCRISY_FILE))
    return out


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


def append_log(pair: dict, result: dict):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {timestamp} — {pair['resolution']}\n\n"
        f"- **Source:** [[{pair['source_slug']}]]\n"
        f"- **Target:** [[{pair['target_slug']}]]\n"
        f"- **Files mutated:** {', '.join(result['mutated_files']) if result['mutated_files'] else '(none)'}\n"
    )
    if result.get("errors"):
        entry += f"- **Errors:** {result['errors']}\n"
    entry += "\n---\n"

    if not os.path.exists(LOG_FILE):
        header = (
            "---\n"
            "nexus:\n  - ora\n"
            "type: working\n"
            "tags:\n  - engram-cleaning\n  - log\n"
            f"date created: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"date modified: {datetime.now().strftime('%Y-%m-%d')}\n"
            "---\n\n"
            "# Engram Cleaning Resolution Log\n\n"
            "*Append-only log of resolutions applied by the Engram Cleaning Framework's resolver. "
            "Each entry records what was mutated; rollback via `git revert` of the resolver's "
            "auto-commit.*\n"
        )
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(header + entry)
    else:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)


# ---------------------------------------------------------------------------
# ChromaDB metadata refresh
# ---------------------------------------------------------------------------


def refresh_chromadb(slugs: set[str]):
    """Refresh ChromaDB metadata for every record belonging to each slug.

    Returns record/file counts for callers that want structured reporting.
    Existing source files with no Chroma records, missing source files, and
    errors are tracked separately so none can be mistaken for a successful
    metadata update.
    """
    if not slugs:
        return {
            "updated_records": 0,
            "updated_files": 0,
            "never_indexed_files": 0,
            "missing_source_files": 0,
            "errors": 0,
        }
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from orchestrator.tools.knowledge_index import (
        _parse_frontmatter,
        _compose_chroma_metadata,
        update_file_metadata,
    )
    from orchestrator.embedding import get_or_create_collection
    import chromadb

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    col = get_or_create_collection(client, COLLECTION_NAME)

    updated_records = 0
    updated_files = 0
    never_indexed_files = 0
    missing_source_files = 0
    errors = 0

    for slug in sorted(slugs):
        path = os.path.join(ENGRAMS_DIR, f"{slug}.md")
        if not os.path.exists(path):
            missing_source_files += 1
            print(f"  ChromaDB source file missing for {slug}: {path}",
                  file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            meta, _body = _parse_frontmatter(content)
            chroma_meta = _compose_chroma_metadata(path, meta)
            record_count = update_file_metadata(col, path, chroma_meta)
        except Exception as e:
            errors += 1
            print(f"  ChromaDB metadata error for {slug}: {e}", file=sys.stderr)
            continue

        if record_count == 0:
            never_indexed_files += 1
        else:
            updated_files += 1
            updated_records += record_count

    print(f"  Refreshed ChromaDB metadata for {updated_records} records "
          f"across {updated_files} source files")
    if never_indexed_files:
        print(f"  Existing source files with no ChromaDB records: "
              f"{never_indexed_files}")
    if missing_source_files:
        print(f"  Missing source files: {missing_source_files}")
    if errors:
        print(f"  ChromaDB metadata errors: {errors}", file=sys.stderr)

    return {
        "updated_records": updated_records,
        "updated_files": updated_files,
        "never_indexed_files": never_indexed_files,
        "missing_source_files": missing_source_files,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_resolver(dry_run: bool = False) -> dict:
    """Public callable for the slash-command handler and CLI.

    Returns a dict with: total_pairs, stats (per-resolution counts),
    affected_slugs_count, errors (list), queue_remaining_count.
    Raises FileNotFoundError if the queue file is missing.
    """
    if not os.path.exists(QUEUE_FILE):
        raise FileNotFoundError(f"Queue file not found: {QUEUE_FILE}")

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue_text = f.read()

    pairs = parse_queue(queue_text)

    stats = {r: 0 for r in VALID_RESOLUTIONS | {"pending"}}
    affected_slugs: set[str] = set()
    resolved_pair_indices: list[int] = []
    errors: list[str] = []

    for i, pair in enumerate(pairs):
        resolution = pair["resolution"]
        if resolution == "pending":
            stats["pending"] += 1
            continue

        if resolution not in VALID_RESOLUTIONS:
            errors.append(f"unknown resolution '{resolution}' on pair {i+1}")
            continue

        result = {"mutated_files": [], "errors": []}

        if resolution == "skip":
            pass
        elif resolution == "changed-mind:source-supersedes-target":
            result = apply_changed_mind(
                survivor_slug=pair["source_slug"],
                archived_slug=pair["target_slug"],
                archived_h1=pair["target_h1"],
                dry_run=dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "changed-mind:target-supersedes-source":
            result = apply_changed_mind(
                survivor_slug=pair["target_slug"],
                archived_slug=pair["source_slug"],
                archived_h1=pair["source_h1"],
                dry_run=dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "wrong:source":
            result = apply_wrong(pair["source_slug"], dry_run=dry_run)
            affected_slugs.add(pair["source_slug"])
        elif resolution == "wrong:target":
            result = apply_wrong(pair["target_slug"], dry_run=dry_run)
            affected_slugs.add(pair["target_slug"])
        elif resolution == "hypocrisy":
            result = apply_hypocrisy(pair, dry_run=dry_run)

        stats[resolution] += 1
        resolved_pair_indices.append(i)

        if not dry_run:
            append_log(pair, result)

        if result.get("errors"):
            errors.extend(result["errors"])

    if not dry_run and affected_slugs:
        refresh_chromadb(affected_slugs)

    if not dry_run and resolved_pair_indices:
        new_text = _rebuild_queue_keeping_pending(queue_text)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(new_text)

    return {
        "total_pairs": len(pairs),
        "stats": stats,
        "affected_slugs_count": len(affected_slugs),
        "errors": errors,
        "queue_remaining_count": stats.get("pending", 0),
        "dry_run": dry_run,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be mutated without writing")
    args = ap.parse_args()

    if not os.path.exists(QUEUE_FILE):
        print(f"Queue file not found: {QUEUE_FILE}", file=sys.stderr)
        print("Run detection first:", file=sys.stderr)
        print("  python3 run_engram_cleaning_detection.py", file=sys.stderr)
        sys.exit(1)

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue_text = f.read()

    pairs = parse_queue(queue_text)
    print(f"Parsed {len(pairs)} pairs from queue")

    stats = {r: 0 for r in VALID_RESOLUTIONS | {"pending"}}
    affected_slugs: set[str] = set()
    resolved_pair_indices: list[int] = []

    for i, pair in enumerate(pairs):
        resolution = pair["resolution"]
        if resolution == "pending":
            stats["pending"] += 1
            continue

        if resolution not in VALID_RESOLUTIONS:
            print(f"  WARN: unknown resolution '{resolution}' — skipping pair {i+1}",
                  file=sys.stderr)
            continue

        result = {"mutated_files": [], "errors": []}

        if resolution == "skip":
            pass  # nothing to do; will remove from queue
        elif resolution == "changed-mind:source-supersedes-target":
            result = apply_changed_mind(
                survivor_slug=pair["source_slug"],
                archived_slug=pair["target_slug"],
                archived_h1=pair["target_h1"],
                dry_run=args.dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "changed-mind:target-supersedes-source":
            result = apply_changed_mind(
                survivor_slug=pair["target_slug"],
                archived_slug=pair["source_slug"],
                archived_h1=pair["source_h1"],
                dry_run=args.dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "wrong:source":
            result = apply_wrong(pair["source_slug"], dry_run=args.dry_run)
            affected_slugs.add(pair["source_slug"])
        elif resolution == "wrong:target":
            result = apply_wrong(pair["target_slug"], dry_run=args.dry_run)
            affected_slugs.add(pair["target_slug"])
        elif resolution == "hypocrisy":
            result = apply_hypocrisy(pair, dry_run=args.dry_run)

        stats[resolution] += 1
        resolved_pair_indices.append(i)

        if not args.dry_run:
            append_log(pair, result)

        if result["mutated_files"]:
            print(f"  [{resolution}] {' '.join(result['mutated_files'])}")
        if result["errors"]:
            print(f"  ERRORS on pair {i+1}: {result['errors']}", file=sys.stderr)

    # Refresh chromadb for affected files
    if not args.dry_run and affected_slugs:
        print("\nRefreshing ChromaDB metadata...")
        refresh_chromadb(affected_slugs)

    # Remove resolved pairs from the queue (rebuild file with pending only)
    if not args.dry_run and resolved_pair_indices:
        new_text = _rebuild_queue_keeping_pending(queue_text)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"Queue updated: removed {len(resolved_pair_indices)} resolved pairs, "
              f"{stats['pending']} still pending")

    # Summary
    print("\n=== Summary ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:45} {v:>4}")
    if args.dry_run:
        print("\nDRY RUN — no files modified.")
    else:
        print(f"\nVault is in git. Review with `git diff` before committing.")
        print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
