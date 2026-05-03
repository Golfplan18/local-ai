"""Vault index builder for the historical chat reprocessing pipeline.

Phase 0 of the historical reprocessing pipeline. Scans the vault for
mature artifacts, computes topic fingerprints + paragraph hashes,
and emits a JSON index that AI consults during Phase 1 cleanup to
spot when pasted material is just an earlier version of something
already in mature form in the vault.

Output: ~/ora/data/vault-index.json

Design:
  - Single-pass scan with skip rules (no follow into Sessions/, .bak,
    conversation-chunk filenames, transient subdirs).
  - Topic fingerprint = sorted, deduplicated key noun phrases joined
    with `|`. Stable across minor edits.
  - Paragraph hashing = SHA-256 prefix over normalized paragraph text
    (lowercased, punctuation stripped, whitespace collapsed). Only
    paragraphs whose normalized form is at least 100 chars are hashed.
  - Resumable: existing index entries with matching mtime are reused
    on incremental update.
  - --rebuild flag forces full rescan ignoring the existing index.

Authority:
  Architecture is captured in
  `~/Documents/vault/Working — Framework — Historical Chat Reprocessing Architecture.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

VAULT_DEFAULT  = os.path.expanduser("~/Documents/vault")
INDEX_DEFAULT  = os.path.expanduser("~/ora/data/vault-index.json")


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------

# Subdirectories whose contents are excluded from the index entirely.
# Sessions/        — conversation chunks (output, not source-of-truth).
# temp/, Incubator/ — transient.
# .git/, .obsidian/ — system dirs.
SKIP_SUBDIRS = frozenset({"Sessions", "temp", "Incubator", ".git", ".obsidian"})

# Filename patterns to skip.
BAK_RE = re.compile(r"\.bak", re.IGNORECASE)
CHUNK_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_.*\.md$")

# YAML `type:` values that indicate a derived artifact (not a source).
SKIP_TYPES = frozenset({"chat", "cleaned-pair"})


def should_skip(path: Path, vault_root: Path) -> bool:
    """Return True if this file should be excluded from the index.

    Skip rules (any one triggers exclusion):
      1. filename contains '.bak' (case-insensitive)
      2. filename matches conversation-chunk pattern YYYY-MM-DD_HH-MM_*.md
      3. any path component (other than the filename) is in SKIP_SUBDIRS
    """
    name = path.name
    if BAK_RE.search(name):
        return True
    if CHUNK_FILENAME_RE.match(name):
        return True
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    # parts[:-1] excludes the filename itself
    for component in rel.parts[:-1]:
        if component in SKIP_SUBDIRS:
            return True
    return False


# ---------------------------------------------------------------------------
# Maturity classification
# ---------------------------------------------------------------------------

# Top-level subdirs containing mature artifacts.
MATURE_SUBDIRS = frozenset({
    "Engrams", "Lenses", "Modes", "Tools", "Templates", "Modules",
    "Library", "Resources",
})

# Top-level subdirs containing working/draft material — indexed but
# flagged mature=False so paste-detection can decide how aggressive to be.
WORKING_SUBDIRS = frozenset({
    "Workshop", "Old AI Working Files", "Clipper",
})


def classify_maturity(path: Path, vault_root: Path) -> bool:
    """Return True if this file is a mature artifact, False if working/draft.

    Top-level vault files are mature.
    Files in MATURE_SUBDIRS are mature.
    Files in WORKING_SUBDIRS are working (mature=False).
    Files in unrecognized subdirs default to mature=True.
    """
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return True
    parts = rel.parts
    if len(parts) <= 1:
        return True
    top = parts[0]
    if top in WORKING_SUBDIRS:
        return False
    return True


# ---------------------------------------------------------------------------
# YAML frontmatter parsing
# ---------------------------------------------------------------------------

YAML_FENCE_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (yaml_dict, body).

    Minimal parser — handles flat key:value and key: list-of-strings.
    Sufficient for the conventions used in this vault.
    """
    m = YAML_FENCE_RE.match(text)
    if not m:
        return {}, text
    yaml_text = m.group(1)
    body = text[m.end():]
    yaml_dict: dict = {}
    current_list_key: Optional[str] = None
    for line in yaml_text.split("\n"):
        if not line.strip():
            current_list_key = None
            continue
        # List item: "  - value" (also accepts "- " at column 0)
        list_match = re.match(r"^\s*-\s+(.*)$", line)
        if list_match and current_list_key:
            yaml_dict.setdefault(current_list_key, []).append(
                list_match.group(1).strip().strip('"\'')
            )
            continue
        # Key:value pair
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"\'')
            if value:
                yaml_dict[key] = value
                current_list_key = None
            else:
                current_list_key = key
                yaml_dict[key] = []
    return yaml_dict, body


def yaml_skip_by_type(yaml_meta: dict) -> bool:
    """Return True if the YAML `type:` says this is a derived artifact."""
    t = yaml_meta.get("type", "")
    if isinstance(t, str):
        return t.strip() in SKIP_TYPES
    return False


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def extract_title(body: str, fallback: str) -> str:
    """Return the first H1 in body, or `fallback` (filename stem)."""
    m = H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return fallback


# ---------------------------------------------------------------------------
# Paragraph hashing
# ---------------------------------------------------------------------------

PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
PUNCT_RE = re.compile(r"[^\w\s]+")
WHITESPACE_RE = re.compile(r"\s+")
MIN_NORMALIZED_CHARS = 100
HASH_PREFIX_LEN = 200
HASH_HEX_LEN = 16


def normalize_paragraph(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = PUNCT_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def paragraph_hashes(body: str) -> list[str]:
    """Hash significant paragraphs of `body`.

    A paragraph is significant if its normalized form is at least
    MIN_NORMALIZED_CHARS long. The hash is the first HASH_HEX_LEN chars
    of SHA-256 over the first HASH_PREFIX_LEN chars of normalized text.
    """
    out: list[str] = []
    for raw in PARAGRAPH_SPLIT_RE.split(body):
        normalized = normalize_paragraph(raw)
        if len(normalized) < MIN_NORMALIZED_CHARS:
            continue
        prefix = normalized[:HASH_PREFIX_LEN]
        digest = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
        out.append(digest[:HASH_HEX_LEN])
    return out


# ---------------------------------------------------------------------------
# Topic fingerprint + key phrases
# ---------------------------------------------------------------------------

# Conservative stop-word list for filtering noisy "key phrase" candidates.
STOP_WORDS = frozenset(
    "the a an of in on at to for with by from as is are was were be been "
    "being have has had do does did will would shall should may might can "
    "could and but or if while because until although since this that these "
    "those it its they them their he his she her you your we our i me my "
    "what which who whom whose how why when where there here also even just "
    "only own same some any all each every both few more most other such no "
    "nor not very still already well make use used using how very".split()
)

CAPITALIZED_PHRASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]+(?:[\-\s]+[A-Z][A-Za-z0-9]+){0,3}\b"
)


def extract_key_phrases(title: str, body: str, max_n: int = 12) -> list[str]:
    """Extract top capitalized noun-phrase candidates from title + opening.

    Strategy:
      - Concatenate title + first 800 chars of body
      - Find capitalized phrases (1–4 words)
      - Drop phrases that are entirely stop-words after lowercasing
      - Dedupe case-insensitively, preserve first-seen capitalization
    """
    sample = (title or "") + "\n" + (body[:800] if body else "")
    seen: set[str] = set()
    out: list[str] = []
    for match in CAPITALIZED_PHRASE_RE.finditer(sample):
        phrase = match.group(0).strip()
        # Collapse internal whitespace runs to single space.
        phrase = re.sub(r"\s+", " ", phrase)
        key = phrase.lower()
        if key in seen:
            continue
        words = re.split(r"[\s\-]+", key)
        if all(w in STOP_WORDS for w in words):
            continue
        if len(key) < 3:
            continue
        seen.add(key)
        out.append(phrase)
        if len(out) >= max_n:
            break
    return out


def topic_fingerprint(key_phrases: list[str], top_n: int = 8) -> str:
    """Sorted lower-cased phrases joined with `|`. Stable across edits."""
    keys = sorted({p.lower().replace(" ", "-") for p in key_phrases})
    return "|".join(keys[:top_n])


# ---------------------------------------------------------------------------
# Index entry + scan
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    id:                str
    vault_path:        str            # path relative to vault root
    title:             str
    topic_fingerprint: str
    paragraph_hashes:  list[str]
    key_phrases:       list[str]
    summary:           str            # one-line summary, ≤120 chars
    mature:            bool
    indexed_at:        str
    file_mtime:        float
    yaml_tags:         list[str] = field(default_factory=list)
    yaml_type:         str = ""


def _summary_from_body(body: str) -> str:
    # Drop leading H1 if present, then take the first ~120 chars of
    # whitespace-collapsed prose.
    body = H1_RE.sub("", body, count=1)
    text = WHITESPACE_RE.sub(" ", body).strip()
    return text[:120]


def build_entry(path: Path, vault_root: Path, entry_id: str,
                yaml_meta: Optional[dict] = None,
                body: Optional[str] = None) -> IndexEntry:
    """Build an IndexEntry from a vault file."""
    if yaml_meta is None or body is None:
        text = path.read_text(encoding="utf-8")
        yaml_meta, body = parse_frontmatter(text)
    title = extract_title(body, fallback=path.stem)
    hashes = paragraph_hashes(body)
    key_phrases = extract_key_phrases(title, body)
    fp = topic_fingerprint(key_phrases)
    summary = _summary_from_body(body)
    mature = classify_maturity(path, vault_root)
    yaml_tags = yaml_meta.get("tags", [])
    if isinstance(yaml_tags, str):
        yaml_tags = [t.strip() for t in yaml_tags.split(",") if t.strip()]
    elif not isinstance(yaml_tags, list):
        yaml_tags = []
    yaml_type = ""
    raw_type = yaml_meta.get("type", "")
    if isinstance(raw_type, str):
        yaml_type = raw_type.strip()
    return IndexEntry(
        id=entry_id,
        vault_path=str(path.relative_to(vault_root)),
        title=title,
        topic_fingerprint=fp,
        paragraph_hashes=hashes,
        key_phrases=key_phrases,
        summary=summary,
        mature=mature,
        indexed_at=datetime.now().isoformat(timespec="seconds"),
        file_mtime=path.stat().st_mtime,
        yaml_tags=yaml_tags,
        yaml_type=yaml_type,
    )


def iter_vault_files(vault_root: Path) -> Iterator[Path]:
    """Yield indexable .md paths under vault_root (skip rules applied)."""
    for path in sorted(vault_root.rglob("*.md")):
        if should_skip(path, vault_root):
            continue
        yield path


# ---------------------------------------------------------------------------
# Build / update
# ---------------------------------------------------------------------------


def _load_existing(output_file: Path) -> tuple[dict, int]:
    """Load existing index. Returns ({rel_path: entry_dict}, next_id)."""
    if not output_file.exists():
        return {}, 1
    try:
        prior = json.loads(output_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, 1
    by_path: dict = {}
    next_id = 1
    for entry in prior.get("entries", []):
        path = entry.get("vault_path", "")
        if not path:
            continue
        by_path[path] = entry
        eid = entry.get("id", "")
        if eid.startswith("vault-"):
            try:
                n = int(eid.split("-", 1)[1])
                next_id = max(next_id, n + 1)
            except ValueError:
                pass
    return by_path, next_id


def build_index(vault_path: str = VAULT_DEFAULT,
                output_path: str = INDEX_DEFAULT,
                rebuild: bool = False,
                progress: bool = False) -> dict:
    """Build or update the vault index.

    Returns a stats dict with counts per category.
    Writes the index JSON to `output_path`.
    """
    vault_root = Path(vault_path).expanduser().resolve()
    output_file = Path(output_path).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    existing, next_id = ({}, 1) if rebuild else _load_existing(output_file)

    entries: list[dict] = []
    stats = {
        "total":         0,
        "new":           0,
        "updated":       0,
        "unchanged":     0,
        "yaml_skipped":  0,
        "errors":        0,
    }

    for path in iter_vault_files(vault_root):
        rel_path = str(path.relative_to(vault_root))
        stats["total"] += 1
        try:
            mtime = path.stat().st_mtime
        except OSError:
            stats["errors"] += 1
            continue

        existing_entry = existing.get(rel_path)
        if (existing_entry
                and not rebuild
                and existing_entry.get("file_mtime") == mtime):
            entries.append(existing_entry)
            stats["unchanged"] += 1
            continue

        # Parse + run yaml-type skip check.
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"warning: read failed {path}: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue

        yaml_meta, body = parse_frontmatter(text)
        if yaml_skip_by_type(yaml_meta):
            stats["yaml_skipped"] += 1
            continue

        # Entry id: reuse if updating, else allocate next.
        if existing_entry:
            entry_id = existing_entry.get("id") or f"vault-{next_id:04d}"
        else:
            entry_id = f"vault-{next_id:04d}"
            next_id += 1

        try:
            entry = build_entry(path, vault_root, entry_id,
                                yaml_meta=yaml_meta, body=body)
            entries.append(asdict(entry))
            if existing_entry:
                stats["updated"] += 1
            else:
                stats["new"] += 1
            if progress and stats["total"] % 100 == 0:
                print(f"  ... {stats['total']} files scanned", file=sys.stderr)
        except Exception as e:
            print(f"warning: entry build failed {path}: {e}", file=sys.stderr)
            stats["errors"] += 1

    output = {
        "version":    1,
        "built_at":   datetime.now().isoformat(timespec="seconds"),
        "vault_path": str(vault_root),
        "stats":      stats,
        "entries":    entries,
    }
    output_file.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return stats


# ---------------------------------------------------------------------------
# Lookup helpers (used by Phase 1)
# ---------------------------------------------------------------------------


def load_index(path: str = INDEX_DEFAULT) -> dict:
    """Load the index JSON. Raises if missing/malformed."""
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def find_matches_by_paragraph_hash(text: str,
                                     index: dict,
                                     min_overlap: float = 0.5,
                                     mature_only: bool = True
                                     ) -> list[dict]:
    """Find vault entries whose paragraph hashes overlap with `text`.

    Returns a list of {entry, overlap_ratio, matching_hashes} dicts,
    sorted by overlap descending. `min_overlap` is the fraction of the
    candidate's hashes that must match; default 0.5.
    """
    candidate_hashes = set(paragraph_hashes(text))
    if not candidate_hashes:
        return []
    matches: list[dict] = []
    for entry in index.get("entries", []):
        if mature_only and not entry.get("mature"):
            continue
        entry_hashes = set(entry.get("paragraph_hashes") or [])
        if not entry_hashes:
            continue
        common = candidate_hashes & entry_hashes
        overlap = len(common) / len(candidate_hashes)
        if overlap >= min_overlap:
            matches.append({
                "entry":            entry,
                "overlap_ratio":    overlap,
                "matching_hashes":  sorted(common),
            })
    matches.sort(key=lambda m: m["overlap_ratio"], reverse=True)
    return matches


def find_matches_by_topic_fingerprint(fingerprint: str,
                                       index: dict) -> list[dict]:
    """Exact-match lookup on topic_fingerprint."""
    out = []
    for entry in index.get("entries", []):
        if entry.get("topic_fingerprint") == fingerprint:
            out.append(entry)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or update the vault index for Phase 0 of the "
                    "historical chat reprocessing pipeline.",
    )
    parser.add_argument("--vault", default=VAULT_DEFAULT,
                        help=f"Vault root path (default: {VAULT_DEFAULT})")
    parser.add_argument("--output", default=INDEX_DEFAULT,
                        help=f"Index JSON output path "
                             f"(default: {INDEX_DEFAULT})")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force full rebuild ignoring existing index.")
    parser.add_argument("--progress", action="store_true",
                        help="Print progress every 100 files.")
    args = parser.parse_args(argv)

    stats = build_index(vault_path=args.vault, output_path=args.output,
                        rebuild=args.rebuild, progress=args.progress)
    print(f"Vault index written to {args.output}")
    print(f"Stats: {json.dumps(stats, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "VAULT_DEFAULT",
    "INDEX_DEFAULT",
    "should_skip",
    "classify_maturity",
    "parse_frontmatter",
    "yaml_skip_by_type",
    "extract_title",
    "normalize_paragraph",
    "paragraph_hashes",
    "extract_key_phrases",
    "topic_fingerprint",
    "IndexEntry",
    "build_entry",
    "iter_vault_files",
    "build_index",
    "load_index",
    "find_matches_by_paragraph_hash",
    "find_matches_by_topic_fingerprint",
]
