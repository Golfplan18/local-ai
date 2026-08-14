"""News Supersession Framework — resolver phase.

Reads the queue file the user edited with resolution markers, applies
mechanical YAML mutations per resolution, refreshes ChromaDB metadata,
and appends to the resolution log.

See `Framework — News Supersession` (vault canonical) for the full spec.

Critical distinction from Engram Cleaning resolver:
    `[changed-mind:source-supersedes-target]` applies the `superseded`
    tag (NOT `archived`) to the loser. `superseded` is a weight modifier
    per Schema §6.5 rev 5.1; the loser stays retrievable at reduced
    weight (0.6) — preserves history at retrieval. `archived` (the
    Engram Cleaning mechanic) would exclude from default retrieval,
    which is wrong for news because news stories develop but they don't
    replace history.

    `[wrong:source]` / `[wrong:target]` retain `archived` semantics —
    factually wrong articles SHOULD be excluded from default retrieval.

Idempotency: each resolution is applied exactly once; running twice is
safe (already-tagged notes are no-ops; supersedes relationships are
deduplicated).

Usage:
    python3 run_news_supersession_resolver.py [--dry-run]

Resolution markers handled:
    [changed-mind:source-supersedes-target]
    [changed-mind:target-supersedes-source]
    [wrong:source]
    [wrong:target]
    [skip]
    [hypocrisy]  — treated as skip with warning (not applicable to news)
    [pending]    — left as-is (skipped this run)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Optional

import yaml


VAULT_ROOT = os.path.expanduser("~/Documents/vault")
RESOURCES_DIR = os.path.join(VAULT_ROOT, "Resources")
QUEUE_FILE = os.path.join(
    VAULT_ROOT, "Projects", "MSI", "Working — News Supersession Queue.md"
)
LOG_FILE = os.path.join(
    VAULT_ROOT, "Projects", "MSI", "Working — News Supersession Log.md"
)

def _chromadb_default() -> str:
    """Resolve the vector store through runtime_paths, never a hardcoded path.

    A literal os.path.expanduser("~/ora/chromadb") ignores ORA_CHROMADB_PATH,
    so it bypassed the test quarantine in orchestrator/tests/live_guard.py and
    read the user's real 7 GB store during unit tests — which is how
    test_rag_isolation_bypass came to run a lexical scan over the live corpus
    and hang the suite. runtime_paths is also what makes these modules portable
    off macOS.
    """
    from orchestrator import runtime_paths as _rp
    return str(_rp.chromadb_dir())


CHROMADB_PATH = _chromadb_default()
COLLECTION_NAME = "knowledge"


VALID_RESOLUTIONS = {
    "changed-mind:source-supersedes-target",
    "changed-mind:target-supersedes-source",
    "wrong:source",
    "wrong:target",
    "skip",
    "hypocrisy",  # accepted but treated as skip with warning
}


# ---------------------------------------------------------------------------
# Queue parsing — uses the same Resolution-line canonical pattern as the
# Engram Cleaning resolver post-2026-05-09 bug fix.
# ---------------------------------------------------------------------------


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

    Canonical resolution marker comes from the `**Resolution:** [marker]`
    line — the user-facing edit point. Heading is informational only.
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
    """Rewrite queue text keeping only sections whose Resolution is [pending]."""
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
# YAML mutations
# ---------------------------------------------------------------------------


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def read_resource(slug: str) -> Optional[tuple[str, str]]:
    """Return (frontmatter, body) for the resource, or None if missing."""
    path = os.path.join(RESOURCES_DIR, f"{slug}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    m = FRONTMATTER_RE.match(content)
    if not m:
        return None
    return m.group(1), m.group(2)


def write_resource(slug: str, frontmatter: str, body: str):
    path = os.path.join(RESOURCES_DIR, f"{slug}.md")
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
    if not indent:
        indent = "  "
    lines.insert(end_idx, f"{indent}- {tag}")
    return "\n".join(lines)


def yaml_escape(s: str) -> str:
    if any(c in s for c in ":#'\"[]{}|*&!%@,\\"):
        return "'" + s.replace("'", "''") + "'"
    return s


def add_supersedes_relationship(frontmatter: str, target_h1: str) -> str:
    """Append a supersedes relationship to the relationships: list (idempotent)."""
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
    rel_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^relationships:\s*$", line):
            rel_idx = i
            break

    if rel_idx is not None:
        end_idx = rel_idx + 1
        while end_idx < len(lines):
            if (lines[end_idx].startswith("- ")
                    or lines[end_idx].startswith("  ")):
                end_idx += 1
            else:
                break
        for offset, new_line in enumerate(new_entry_lines):
            lines.insert(end_idx + offset, new_line)
    else:
        insert_idx = len(lines)
        for i, line in enumerate(lines):
            if re.match(r"^date created:", line):
                insert_idx = i
                break
        new_block = ["relationships:"] + new_entry_lines
        for offset, new_line in enumerate(new_block):
            lines.insert(insert_idx + offset, new_line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resolution dispatch
# ---------------------------------------------------------------------------


def apply_supersession(survivor_slug: str, loser_slug: str,
                       loser_h1: str, dry_run: bool) -> dict:
    """Apply news supersession: survivor gets `supersedes` relationship;
    loser gets `superseded` tag (NOT archived — Schema rev 5.1 weight
    modifier preserving history at retrieval).
    """
    out: dict = {"mutated_files": [], "errors": []}

    survivor = read_resource(survivor_slug)
    if survivor is None:
        out["errors"].append(f"survivor not found: {survivor_slug}")
        return out
    loser = read_resource(loser_slug)
    if loser is None:
        out["errors"].append(f"loser not found: {loser_slug}")
        return out

    s_fm, s_body = survivor
    l_fm, l_body = loser

    new_s_fm = add_supersedes_relationship(s_fm, loser_h1)
    new_l_fm = add_tag(l_fm, "superseded")

    if not dry_run:
        if new_s_fm != s_fm:
            write_resource(survivor_slug, new_s_fm, s_body)
            out["mutated_files"].append(f"{survivor_slug}.md")
        if new_l_fm != l_fm:
            write_resource(loser_slug, new_l_fm, l_body)
            out["mutated_files"].append(f"{loser_slug}.md")
    else:
        if new_s_fm != s_fm:
            out["mutated_files"].append(
                f"[dry-run] {survivor_slug}.md (+supersedes)"
            )
        if new_l_fm != l_fm:
            out["mutated_files"].append(
                f"[dry-run] {loser_slug}.md (+superseded tag)"
            )

    return out


def apply_wrong(slug: str, dry_run: bool) -> dict:
    """Factually wrong article → add `archived` tag (same as Engram Cleaning)."""
    out: dict = {"mutated_files": [], "errors": []}
    target = read_resource(slug)
    if target is None:
        out["errors"].append(f"not found: {slug}")
        return out
    fm, body = target
    new_fm = add_tag(fm, "archived")
    if not dry_run:
        if new_fm != fm:
            write_resource(slug, new_fm, body)
            out["mutated_files"].append(f"{slug}.md")
    else:
        if new_fm != fm:
            out["mutated_files"].append(f"[dry-run] {slug}.md (+archived tag)")
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
        f"- **Files mutated:** "
        f"{', '.join(result['mutated_files']) if result['mutated_files'] else '(none)'}\n"
    )
    if result.get("errors"):
        entry += f"- **Errors:** {result['errors']}\n"
    entry += "\n---\n"

    if not os.path.exists(LOG_FILE):
        header = (
            "---\n"
            "nexus:\n  - ora\n"
            "type: working\n"
            "tags:\n  - news-supersession\n  - log\n"
            f"date created: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"date modified: {datetime.now().strftime('%Y-%m-%d')}\n"
            "---\n\n"
            "# News Supersession Resolution Log\n\n"
            "*Append-only log of resolutions applied by the News Supersession Framework's resolver. "
            "Each entry records what was mutated; rollback via `git revert` of the resolver's commit.*\n"
        )
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(header + entry)
    else:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)


# ---------------------------------------------------------------------------
# ChromaDB metadata refresh
# ---------------------------------------------------------------------------


def refresh_chromadb(slugs: set[str]) -> dict:
    """Refresh metadata on every Chroma record belonging to ``slugs``.

    Returns an explicit summary so callers can distinguish successfully
    updated physical records from existing files that were never indexed,
    missing source files, and actual update failures.  The return value is
    additive/backward-compatible: existing slash-command and sweep callers
    that ignore it continue to work.
    """
    summary = {
        "updated_records": 0,
        "updated_files": 0,
        "never_indexed_files": 0,
        "missing_source_files": 0,
        "errors": 0,
        "never_indexed_slugs": [],
        "missing_source_slugs": [],
        "error_messages": [],
    }
    if not slugs:
        return summary
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

    for slug in sorted(slugs):
        path = os.path.abspath(os.path.join(RESOURCES_DIR, f"{slug}.md"))
        if not os.path.exists(path):
            summary["missing_source_files"] += 1
            summary["missing_source_slugs"].append(slug)
            print(f"  ChromaDB source file missing for {slug}: {path}",
                  file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            meta, _body = _parse_frontmatter(content)
            chroma_meta = _compose_chroma_metadata(path, meta)
            updated = update_file_metadata(col, path, chroma_meta)
            if updated == 0:
                summary["never_indexed_files"] += 1
                summary["never_indexed_slugs"].append(slug)
            else:
                summary["updated_files"] += 1
                summary["updated_records"] += updated
        except Exception as e:
            error = f"chromadb metadata refresh failed for {slug}: {e}"
            summary["errors"] += 1
            summary["error_messages"].append(error)
            print(f"  {error}", file=sys.stderr)

    print(
        "  Refreshed ChromaDB metadata for "
        f"{summary['updated_records']} records across "
        f"{summary['updated_files']} source files"
    )
    if summary["never_indexed_files"]:
        print(
            "  Existing source files with no ChromaDB records: "
            f"{summary['never_indexed_files']} "
            f"({', '.join(summary['never_indexed_slugs'])})"
        )
    if summary["missing_source_files"]:
        print(
            "  Missing source files: "
            f"{summary['missing_source_files']} "
            f"({', '.join(summary['missing_source_slugs'])})"
        )
    if summary["errors"]:
        print(
            f"  ChromaDB metadata errors: {summary['errors']}",
            file=sys.stderr,
        )
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_resolver(dry_run: bool = False) -> dict:
    """Public callable for the slash-command handler and CLI.

    Returns a dict with: total_pairs, stats (per-resolution counts),
    affected_slugs_count, errors (list), queue_remaining_count.
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

        result: dict = {"mutated_files": [], "errors": []}

        if resolution == "skip":
            pass
        elif resolution == "hypocrisy":
            errors.append(
                f"pair {i+1}: [hypocrisy] not applicable to news; "
                f"treated as skip. Use [skip] explicitly."
            )
            # Treat as skip — no mutation; just log
        elif resolution == "changed-mind:source-supersedes-target":
            result = apply_supersession(
                survivor_slug=pair["source_slug"],
                loser_slug=pair["target_slug"],
                loser_h1=pair["target_h1"],
                dry_run=dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "changed-mind:target-supersedes-source":
            result = apply_supersession(
                survivor_slug=pair["target_slug"],
                loser_slug=pair["source_slug"],
                loser_h1=pair["source_h1"],
                dry_run=dry_run,
            )
            affected_slugs.update([pair["source_slug"], pair["target_slug"]])
        elif resolution == "wrong:source":
            result = apply_wrong(pair["source_slug"], dry_run=dry_run)
            affected_slugs.add(pair["source_slug"])
        elif resolution == "wrong:target":
            result = apply_wrong(pair["target_slug"], dry_run=dry_run)
            affected_slugs.add(pair["target_slug"])

        stats[resolution] += 1
        resolved_pair_indices.append(i)

        if not dry_run:
            append_log(pair, result)

        if result.get("errors"):
            errors.extend(result["errors"])

    refresh_result = None
    if not dry_run and affected_slugs:
        refresh_result = refresh_chromadb(affected_slugs)
        errors.extend(refresh_result["error_messages"])

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
        "chromadb_refresh": refresh_result,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(QUEUE_FILE):
        print(f"Queue file not found: {QUEUE_FILE}", file=sys.stderr)
        print("Run detection first:", file=sys.stderr)
        print("  python3 run_news_supersession_detection.py", file=sys.stderr)
        sys.exit(1)

    result = run_resolver(dry_run=args.dry_run)

    print(f"Total pairs: {result['total_pairs']}")
    print(f"Stats: {result['stats']}")
    print(f"Affected files: {result['affected_slugs_count']}")
    print(f"Queue remaining: {result['queue_remaining_count']} pending")

    if result["errors"]:
        print(f"\nErrors: {len(result['errors'])}")
        for e in result["errors"][:10]:
            print(f"  {e}")
        sys.exit(1)

    if args.dry_run:
        print("\nDRY RUN — no files modified.")
    else:
        print(f"\nVault is in git. Review with `git diff` before committing.")
        print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
