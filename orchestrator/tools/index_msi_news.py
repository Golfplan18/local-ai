#!/usr/bin/env python3
"""Index the MSI News mirror into the Ora `knowledge` collection.

`~/Documents/vault/MSI News/` is a one-way `rsync -az --delete` mirror of
the cloud MSI pipeline's `cloud-outbox/msi-news/` (launchd job
`com.cloud-ora.sync`, every 15 min). Its on-disk .md files do NOT carry
Ora schema frontmatter, and any local stamp would be reverted on the next
sync. So this indexer FORCES the schema at index time via
`knowledge_index.index_file`'s `meta_overrides`, without modifying files:

    type  : resource                  -> provenance weight 0.8 (Ora YAML Schema)
    nexus : [main-street-independent]  -> MSI namespace marker (Tagging Schema §D)
    tags  : [news, main-street-independent, msi-news]
            -> §A genre + namespace tag + the `msi-news` scoping tag,
               registered in knowledge_index._FILTERABLE_TAGS so a mode's
               `### exclude_tags` RAG profile can scope MSI news in/out of
               the knowledge lane. (Default: included, at weight 0.8.)

A knowledge_v2 doc persists once written, regardless of later file
reverts. This module is the runtime indexing path for MSI news: called by
the post-rsync hook in ~/cloud-ora-sync/sync.py (index exactly what the
sync changed — no separate cron, per the Runtime Principle), and runnable
standalone for the initial catch-up over the existing mirror.

Usage:
    python3 -m orchestrator.tools.index_msi_news              # index new files in the folder
    python3 -m orchestrator.tools.index_msi_news --force      # re-index the whole folder
    python3 -m orchestrator.tools.index_msi_news [--force] PATH [PATH ...]   # specific files
"""
from __future__ import annotations

import glob
import os
import re
import sys
from typing import Optional

from orchestrator.tools.knowledge_index import index_file, strip_markdown_sections

VAULT = os.environ.get("ORA_VAULT") or os.path.expanduser("~/Documents/vault")
MSI_NEWS = os.path.join(VAULT, "MSI News")
CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")

# Forced Ora-schema metadata for every MSI News article. Single source of
# truth for the MSI knowledge-RAG identity.
MSI_META_OVERRIDES = {
    "type": "resource",
    "nexus": ["main-street-independent"],
    "tags": ["news", "main-street-independent", "msi-news"],
}

# Non-content apparatus stripped from every article body before indexing:
# the per-source citation blocks and the atomic-claim decomposition are
# generation-pipeline metadata, not article prose, and they drown the
# semantic signal for both the embedder and the retrieved document.
# A small minority of articles emit the generation notice as its own H2
# section ("## AI disclosure / CC0", "## Disclosure") instead of a
# trailing paragraph — those section titles are stripped too.
MSI_STRIP_SECTIONS = (
    "Sources",
    "Atomic claims",
    "AI disclosure / CC0",
    "AI disclosure",
    "Disclosure",
)

# Trailing generation notice: a closing paragraph, usually preceded by a
# "---" horizontal rule, canonically
#   ---
#   *This article was generated algorithmically by Main Street
#   Independent's ... framework ...*
# The corpus carries many variants — no italics, "_..._" italics,
# "*AI disclosure: ..." / "AI-generation disclosure footer: ..." lead-ins,
# "This story was generated algorithmically", "is licensed under CC0 and
# was generated algorithmically", stacked double notices, and a rule line
# AFTER the notice — so the match is on the core marker phrase appearing
# anywhere in the FINAL paragraph, not on a literal prefix.
_BOILERPLATE_MARKER = "generated algorithmically"

# Horizontal-rule line: three or more dashes ("----" occurs in corpus).
_HR_RE = re.compile(r"^\s*-{3,}\s*$")

# Short trailing license footer ("*License: CC0 (public domain).*",
# "**License:** Public domain (CC0)", "This work is released under the
# Creative Commons CC0...", "© 2026 ... Licensed under CC0."). Phrasing
# varies wildly across the corpus, so this is a keyword search bounded
# by paragraph length (< 300 chars); it is only ever stripped alongside
# a generation notice, never on its own.
_LICENSE_FOOTER_RE = re.compile(
    r"cc0|creative\s*commons|public[- ]domain|creativecommons\.org",
    re.IGNORECASE,
)


def _final_paragraph_start(text: str) -> int:
    """Index just past the last blank-line boundary (0 if none)."""
    last = None
    for m in re.finditer(r"\n[ \t]*\n", text):
        last = m
    return last.end() if last else 0


def _strip_trailing_boilerplate(body: str) -> str:
    """Drop the trailing generation-notice footer.

    Walks paragraphs bottom-up, collecting footer-ish paragraphs: the
    notice itself (marker phrase), bare horizontal rules (the corpus puts
    them before AND after the notice), and short license/CC0 lines that
    trail the notice. Stops at the first real-content paragraph. The
    collected tail is dropped ONLY if it actually contains a generation
    notice — a lone trailing rule or license mention is left untouched,
    as is a notice followed by real content (not trailing)."""
    text = body.rstrip()
    saw_marker = False
    while text:
        para_start = _final_paragraph_start(text)
        para = text[para_start:]
        if _BOILERPLATE_MARKER in para:
            saw_marker = True
        elif _HR_RE.match(para):
            pass  # rule adjacent to the footer — collect
        elif len(para) < 300 and _LICENSE_FOOTER_RE.search(para):
            pass  # short license line beside the notice — collect
        elif para.lstrip().startswith(("<!--", "<script")):
            pass  # build artifacts (JSON-LD, HTML comments) — collect
        else:
            break
        text = text[:para_start].rstrip()
    if not saw_marker:
        return body
    return text


def msi_body_filter(body: str) -> str:
    """Reduce an MSI News article body to its indexable content: keep the
    summary bullets and article prose; drop Sources, Atomic claims, and
    the trailing generation boilerplate. Passed to index_file as
    body_filter, so it shapes both the stored document and the embed
    text."""
    body = strip_markdown_sections(body, MSI_STRIP_SECTIONS)
    body = _strip_trailing_boilerplate(body)
    return body.strip()


def _collection():
    import chromadb
    from orchestrator.embedding import get_or_create_collection
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    return get_or_create_collection(client, "knowledge")


def index_msi_news(
    paths: Optional[list[str]] = None,
    *,
    force: bool = False,
    collection=None,
) -> dict[str, int]:
    """Index MSI News articles into knowledge_v2 with forced MSI metadata.

    paths defaults to every .md in the MSI News mirror. Returns the
    {indexed, skipped, errors} stats dict. Files shorter than 50 chars or
    unreadable are skipped/counted by index_file.

    force=True re-embeds and re-stores every file even if already indexed
    (delete-then-add per file) — the full forced re-index path. Progress
    prints every 100 files instead of per-file output.
    """
    col = collection if collection is not None else _collection()
    if paths is None:
        paths = sorted(glob.glob(os.path.join(MSI_NEWS, "*.md")))
    stats = {"indexed": 0, "skipped": 0, "errors": 0}
    total = len(paths)
    for i, p in enumerate(paths, 1):
        try:
            index_file(col, p, stats,
                       meta_overrides=MSI_META_OVERRIDES, force=force,
                       body_filter=msi_body_filter, verbose=False)
        except Exception as e:
            stats["errors"] += 1
            print(f"  ERROR indexing {os.path.basename(p)}: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
        if i % 100 == 0 or i == total:
            print(f"  [{i}/{total}] indexed={stats['indexed']} "
                  f"skipped={stats['skipped']} errors={stats['errors']}",
                  flush=True)
    return stats


def remove_paths(paths: list[str], *, collection=None) -> int:
    """Delete the given files' docs from knowledge_v2 (id = absolute path).

    Used by the sync hook to drop articles that the rsync `--delete`
    removed from the mirror, so knowledge_v2 doesn't retain orphans.
    Returns the count of ids requested for deletion.
    """
    col = collection if collection is not None else _collection()
    ids = [os.path.abspath(p) for p in paths]
    if ids:
        try:
            col.delete(ids=ids)
        except Exception as e:
            print(f"  remove error: {type(e).__name__}: {e}", file=sys.stderr)
    return len(ids)


def main(argv: list[str]) -> None:
    force = "--force" in argv
    paths = [a for a in argv if a != "--force"] or None
    col = _collection()
    stats = index_msi_news(paths, force=force, collection=col)
    print(f"MSI index done: {stats}")
    print(f"knowledge_v2 total: {col.count()}")


if __name__ == "__main__":
    main(sys.argv[1:])
