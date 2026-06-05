"""engram_promotion.py — promote runtime-staged notes into vault engrams.

The runtime pipeline (runtime_pipeline.py) extracts atomic notes from each Ora
session, quality-gates them, enriches them with relationships, and writes them
to ``~/ora/data/extraction-staging/`` as ``type: working`` notes. Nothing
previously promoted those into the vault as engrams — so the conversation→engram
loop never closed (notes sat in staging; only the historical import wrote
engrams directly).

This module performs that final step: flip a staged note to ``type: engram``,
fold its ``subtype`` into ``tags`` (the engram note-type convention), give it the
canonical ``YYYY-MM-DD_<slug>.md`` filename, write it into the vault Engrams/
folder, index it into ChromaDB, and archive the staged copy so it isn't
re-promoted. Used by:
  - ``runtime_pipeline`` (final step, behind ORA_RUNTIME_ENGRAM_PROMOTION) —
    closes the loop for every future session;
  - ``scripts/promote_staging_to_engrams.py`` — one-time backlog promotion.

Reuses ``vault_export._slugify`` for filename parity with the historical writer
and ``knowledge_index.index_file`` for indexing (the same function the runtime
pipeline's chromadb step uses).
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys

import yaml

ORA_HOME = os.environ.get("ORA_HOME") or os.path.expanduser("~/ora")
if ORA_HOME not in sys.path:
    sys.path.insert(0, ORA_HOME)

STAGING_DIR = os.path.expanduser("~/ora/data/extraction-staging/")
PROMOTED_DIR = os.path.expanduser("~/ora/data/extraction-promoted/")
VAULT_ENGRAMS = os.path.expanduser("~/Documents/vault/Engrams/")


def _slug(text: str) -> str:
    from orchestrator.vault_export import _slugify
    return _slugify(text) or "untitled"


def _parse(path: str) -> tuple[dict, str]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    return (fm if isinstance(fm, dict) else {}), text[end + 4:].lstrip("\n")


def _title_from(fm: dict, body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _to_engram_fm(fm: dict, date_str: str) -> dict:
    """Transform a staged note's frontmatter into engram frontmatter:
    ``type: engram``, note-type subtype folded into ``tags``, dates +
    provenance marker added. (No ``ai-derived`` tag — runtime atomics are
    weighted uniformly; the AI/user weight gap is being retired separately.)"""
    fm = dict(fm)
    fm["type"] = "engram"
    tags = fm.get("tags") or []
    tags = [t for t in (tags if isinstance(tags, list) else [tags]) if t]
    sub = fm.pop("subtype", None)
    if sub and sub not in tags:
        tags.append(sub)
    if "atomic" not in tags:
        tags.insert(0, "atomic")
    fm["tags"] = tags
    fm.setdefault("date created", date_str)
    fm["date modified"] = date_str
    fm.setdefault("source_platform", "ora-local")  # provenance: runtime-extracted
    return fm


def _dest_path(title: str, date_str: str, dest_dir: str) -> str:
    slug = _slug(title)
    path = os.path.join(dest_dir, f"{date_str}_{slug}.md")
    n = 1
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"{date_str}_{slug}-{n}.md")
        n += 1
    return path


def staging_note_to_engram(staging_path: str, *, vault_engrams: str = VAULT_ENGRAMS,
                           promoted_dir: str = PROMOTED_DIR, index: bool = True,
                           dry_run: bool = False) -> dict:
    """Promote one staged note to a vault engram. Returns a dict with src/dest
    (and ``preview`` in dry-run). Raises only on unexpected I/O; the caller
    (runtime pipeline) wraps in try/except so a single bad note can't break the
    session's post-processing."""
    fm, body = _parse(staging_path)
    date_str = datetime.date.fromtimestamp(os.path.getmtime(staging_path)).isoformat()
    title = _title_from(fm, body, os.path.basename(staging_path).rsplit(".", 1)[0])
    eng_fm = _to_engram_fm(fm, date_str)
    dest = _dest_path(title, date_str, vault_engrams)
    out = ("---\n" + yaml.dump(eng_fm, sort_keys=False, allow_unicode=True).rstrip()
           + "\n---\n\n" + body.rstrip() + "\n")
    if dry_run:
        return {"src": staging_path, "dest": dest, "preview": out, "indexed": False}
    os.makedirs(vault_engrams, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    indexed = False
    if index:
        try:
            from orchestrator.tools.knowledge_index import index_file
            index_file(dest)
            indexed = True
        except Exception as exc:  # noqa: BLE001 — indexing is best-effort
            print(f"[engram_promotion] index failed for {os.path.basename(dest)}: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
    os.makedirs(promoted_dir, exist_ok=True)
    try:
        shutil.move(staging_path, os.path.join(promoted_dir, os.path.basename(staging_path)))
    except Exception:  # noqa: BLE001 — archival is best-effort; engram already written
        pass
    return {"src": staging_path, "dest": dest, "indexed": indexed}


def promote_staging_dir(staging_dir: str = STAGING_DIR, *,
                        vault_engrams: str | None = None,
                        promoted_dir: str | None = None,
                        index: bool = True, dry_run: bool = False,
                        limit: int = 0) -> dict:
    """Promote every staged note in ``staging_dir`` to a vault engram. Returns
    ``{"promoted": n, "results": [...]}``. A note that fails is logged and
    skipped (never aborts the batch). Dest dirs default to the module constants
    but are overridable (used by tests)."""
    if not os.path.isdir(staging_dir):
        return {"promoted": 0, "results": []}
    vault_engrams = vault_engrams or VAULT_ENGRAMS
    promoted_dir = promoted_dir or PROMOTED_DIR
    files = sorted(f for f in os.listdir(staging_dir) if f.endswith(".md"))
    if limit:
        files = files[:limit]
    results = []
    for name in files:
        try:
            results.append(
                staging_note_to_engram(os.path.join(staging_dir, name),
                                       vault_engrams=vault_engrams,
                                       promoted_dir=promoted_dir,
                                       index=index, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001 — one bad note must not abort the batch
            print(f"[engram_promotion] promote failed for {name}: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
    return {"promoted": len(results), "results": results}


__all__ = ["staging_note_to_engram", "promote_staging_dir",
           "STAGING_DIR", "PROMOTED_DIR", "VAULT_ENGRAMS"]
