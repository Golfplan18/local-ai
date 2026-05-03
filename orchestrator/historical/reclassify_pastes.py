"""Re-classify pasted segments in cleaned-pair files using the improved
classifier (platform-aware + headline + webpage garbage detection).

Walks every cleaned-pair file in `~/Documents/Commercial AI archives/`,
re-runs `process_user_input` on its `cleaned_user_input` text using the
new classifier, and rewrites the `#### Pasted segments` annotation block
when classifications change. The file's actual cleaned text (User input
+ Assistant response sections) is left untouched — this is purely a
metadata refresh.

Why this is safe to re-run: paste content is preserved VERBATIM in
`cleaned_user_input` (Phase 1 never sent pasted segments to the model).
The detector finds the same segments on re-run; only the `classification`
field changes per the new scoring rules.

This module exposes the orchestration function `reclassify_archive` and
a small CLI entry-point for batch runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)
from orchestrator.historical.paste_detection import (
    Segment,
    process_user_input,
)
from orchestrator.tools.vault_indexer import (
    INDEX_DEFAULT,
    load_index,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ARCHIVE_DIR     = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_REPORT_PATH     = "/Users/oracle/ora/data/reclassify-report.json"


# ---------------------------------------------------------------------------
# Status mapping (mirrors writer._STATUS_FOR_CLASS)
# ---------------------------------------------------------------------------

_STATUS_FOR_CLASS = {
    "news":           "extract-news",
    "opinion":        "extract-with-context",
    "resource":       "extract-resource",
    "earlier-draft":  "mention-only",
    "other":          "review",
    "":               "unclassified",
}


# ---------------------------------------------------------------------------
# Annotation block (re)builder
# ---------------------------------------------------------------------------


def _format_pasted_segments_block(pasted: list[Segment]) -> str:
    """Build the `#### Pasted segments` annotation block from segments,
    matching writer._format_pasted_segment_annotations exactly so the
    file format stays consistent."""
    if not pasted:
        return ""
    out: list[str] = ["#### Pasted segments", ""]
    for i, seg in enumerate(pasted, start=1):
        cls = seg.classification or "unclassified"
        status = _STATUS_FOR_CLASS.get(cls, "review")
        first_line = (seg.content or "").splitlines()[0] if seg.content else ""
        marker = first_line[:60].strip() or "(empty)"
        out.append(f"- **Segment {i}** — type=`{cls}`, status=`{status}`")
        out.append(f"  - Source marker: `{marker}`")
        if seg.vault_match:
            vid = seg.vault_match.get("id", "?")
            vpath = seg.vault_match.get("vault_path", "?")
            overlap = seg.vault_match.get("overlap_ratio")
            overlap_pct = (
                f"{int(overlap * 100)}%"
                if isinstance(overlap, float) else "?"
            )
            out.append(f"  - Vault index match: `{vid}` (`{vpath}`) — overlap {overlap_pct}")
        else:
            out.append("  - Vault index match: none")
        if seg.heuristic_flags:
            flags = ", ".join(seg.heuristic_flags[:8])
            extra = (
                f" (+{len(seg.heuristic_flags) - 8} more)"
                if len(seg.heuristic_flags) > 8 else ""
            )
            out.append(f"  - Heuristic flags: {flags}{extra}")
        if seg.confidence:
            out.append(f"  - Confidence: {seg.confidence:.2f}")
        out.append(f"  - Length: {len(seg.content or '')} chars")
    return "\n".join(out) + "\n"


# Regex that finds the existing Pasted segments block (the optional
# subsection between `### User input` content and `### Assistant response`).
_PASTED_BLOCK_RE = re.compile(
    r"\n#### Pasted segments\b.*?(?=\n### Assistant response\b)",
    re.DOTALL,
)
# Where to insert the block when there isn't one currently — right
# before the `### Assistant response` heading.
_AI_HEADING_RE = re.compile(r"\n### Assistant response\b")


def _rewrite_pasted_segments_in_file(
    file_path: str,
    new_block: str,
) -> bool:
    """Rewrite the `#### Pasted segments` block in a cleaned-pair file.

    Returns True if the file was modified. The block is replaced if
    present, inserted before `### Assistant response` if absent. If
    `new_block` is empty (no pasted segments now), any existing block
    is removed.
    """
    p = Path(file_path)
    text = p.read_text(encoding="utf-8")
    has_block = bool(_PASTED_BLOCK_RE.search(text))

    if not new_block:
        if has_block:
            new_text = _PASTED_BLOCK_RE.sub("", text)
        else:
            return False
    else:
        if has_block:
            new_text = _PASTED_BLOCK_RE.sub("\n" + new_block, text)
        else:
            new_text = _AI_HEADING_RE.sub(
                "\n" + new_block + "\n### Assistant response",
                text, count=1,
            )

    if new_text == text:
        return False
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(p)
    return True


# ---------------------------------------------------------------------------
# Per-file reclassification
# ---------------------------------------------------------------------------


def reclassify_one_file(
    file_path: str,
    *,
    vault_index: Optional[dict] = None,
) -> dict:
    """Re-classify pasted segments in a single cleaned-pair file.

    Returns a dict with stats and per-segment class change info.
    """
    cp = load_cleaned_pair(file_path)
    new_segments = process_user_input(
        cp.cleaned_user_input,
        vault_index=vault_index,
        source_platform=cp.source_platform,
    )
    pasted = [s for s in new_segments if s.kind == "pasted"]
    new_classes: list[str] = [s.classification or "other" for s in pasted]

    # Compose the new annotation block.
    new_block = _format_pasted_segments_block(pasted)

    # Read the OLD classifications by extracting them from the existing
    # annotation block (cheap regex over the file text).
    old_classes = _extract_old_classifications(file_path)

    changed = (old_classes != new_classes)
    written = False
    if changed:
        written = _rewrite_pasted_segments_in_file(file_path, new_block)

    return {
        "file":            file_path,
        "platform":        cp.source_platform,
        "old_classes":     old_classes,
        "new_classes":     new_classes,
        "n_old":           len(old_classes),
        "n_new":           len(new_classes),
        "changed":         changed,
        "written":         written,
    }


_TYPE_TAG_RE = re.compile(r"type=`([^`]+)`")


def _extract_old_classifications(file_path: str) -> list[str]:
    """Pull existing classification labels from a file's Pasted segments
    annotation, preserving order. Empty list if no annotation block."""
    text = Path(file_path).read_text(encoding="utf-8")
    block_m = _PASTED_BLOCK_RE.search(text)
    if not block_m:
        return []
    return _TYPE_TAG_RE.findall(block_m.group(0))


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------


def reclassify_archive(
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
    *,
    vault_index_path: str = INDEX_DEFAULT,
    progress_to_stderr: bool = True,
    limit: Optional[int] = None,
) -> dict:
    """Walk the cleaned-pair archive and reclassify every file.

    Returns aggregate stats including before/after class distribution.
    """
    start = time.monotonic()

    # Load vault index once (used for earlier-draft override).
    try:
        vault_index = load_index(vault_index_path)
    except Exception as e:
        if progress_to_stderr:
            print(f"[reclass] vault index unavailable ({e}); proceeding "
                  f"without earlier-draft lookup", file=sys.stderr)
        vault_index = {"entries": []}

    files = sorted(Path(archive_dir).glob("*.md"))
    if limit:
        files = files[:limit]
    if progress_to_stderr:
        print(f"[reclass] {len(files):,} cleaned-pair files to scan",
              file=sys.stderr, flush=True)

    before_counts: Counter[str] = Counter()
    after_counts:  Counter[str] = Counter()
    files_changed = 0
    files_unchanged = 0
    files_errored = 0
    transitions: Counter[tuple[str, str]] = Counter()
    by_platform_before: dict[str, Counter[str]] = defaultdict(Counter)
    by_platform_after:  dict[str, Counter[str]] = defaultdict(Counter)

    for i, f in enumerate(files):
        try:
            r = reclassify_one_file(str(f), vault_index=vault_index)
        except Exception as e:
            files_errored += 1
            continue
        before_counts.update(r["old_classes"])
        after_counts.update(r["new_classes"])
        by_platform_before[r["platform"]].update(r["old_classes"])
        by_platform_after[r["platform"]].update(r["new_classes"])
        # Record per-segment transitions where order matches
        n = min(len(r["old_classes"]), len(r["new_classes"]))
        for k in range(n):
            if r["old_classes"][k] != r["new_classes"][k]:
                transitions[(r["old_classes"][k], r["new_classes"][k])] += 1
        if r["changed"]:
            files_changed += 1
        else:
            files_unchanged += 1
        if progress_to_stderr and (i + 1) % 1000 == 0:
            print(f"[reclass] {i+1:,}/{len(files):,} "
                  f"({time.monotonic()-start:.0f}s) "
                  f"changed={files_changed:,}",
                  file=sys.stderr, flush=True)

    return {
        "files_total":    len(files),
        "files_changed":  files_changed,
        "files_unchanged": files_unchanged,
        "files_errored":  files_errored,
        "before_class_counts": dict(before_counts),
        "after_class_counts":  dict(after_counts),
        "transitions":    {f"{a}→{b}": n for (a, b), n in transitions.most_common()},
        "by_platform_before": {k: dict(v) for k, v in by_platform_before.items()},
        "by_platform_after":  {k: dict(v) for k, v in by_platform_after.items()},
        "duration_secs":  time.monotonic() - start,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-classify pasted segments in the cleaned-pair archive.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--vault-index", default=INDEX_DEFAULT)
    parser.add_argument("--limit", type=int,
                          help="Process only N files (for testing)")
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH,
                          help="Write JSON report to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    stats = reclassify_archive(
        archive_dir=args.archive_dir,
        vault_index_path=args.vault_index,
        progress_to_stderr=not args.quiet,
        limit=args.limit,
    )

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_REPORT_PATH",
    "reclassify_one_file",
    "reclassify_archive",
    "main",
]
