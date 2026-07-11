"""Repair cleaned-pair files damaged by the Refusal Leak.

The 2026-04/05 historical run persisted cleanup-model refusals as
cleaned content in several hundred pairs (the failure mode is now
structurally impossible — see prompts.REFUSAL_SIGNATURES and the
guards in pair_cleanup). This module repairs the damage in place:

  Scan phase (`--scan`):
    Walk the cleaned-pair archive, flag files whose User input or
    Assistant response section carries a refusal signature, and apply
    the guard's immunity rule retroactively against the RAW source —
    a signature that also appears in the raw pair is genuine content
    (e.g. the user's own conversations about this pipeline) and is
    excluded. Raw sources are resolved through the archive relocation
    (`~/Documents/conversations/raw/` → `~/Documents/Raw Chat
    Archive/raw/`). Writes `~/ora/data/refusal-repair-list.json`.

  Repair phase (`--repair`):
    For each damaged file: re-parse the raw chat, re-clean the pair
    through the current pipeline (prompts v2 + guards, any backend),
    and surgically replace the file's `## Exchange` block. The
    filename, thread links, and session context are preserved so
    prior_pair / next_pair chains and the chain index stay intact;
    the pair-context keyword sentence is regenerated from the
    repaired content. Frontmatter `processing_model` / `processed_at`
    / `date modified` are updated.

CLI:

    /opt/homebrew/bin/python3 -m orchestrator.historical.repair_refusal_pairs \
        --scan
    /opt/homebrew/bin/python3 -m orchestrator.historical.repair_refusal_pairs \
        --repair --backend claude-cli
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator.historical.cleanup_backends import (
    BACKEND_CHOICES,
    BACKEND_CLAUDE_CLI,
    CLI_RECOMMENDED_MAX_WORKERS,
    build_client,
)
from orchestrator.historical.context_header import extract_keywords
from orchestrator.historical.pair_cleanup import CleanedPair, clean_pair
from orchestrator.historical.parser import parse_raw_chat_file
from orchestrator.historical.prompts import REFUSAL_SIGNATURES
from orchestrator.historical.writer import (
    _format_engagement_strip_log,
    _format_pasted_segment_annotations,
)
from orchestrator.tools.vault_indexer import INDEX_DEFAULT, load_index


DEFAULT_ARCHIVE_DIR = os.path.expanduser("~/Documents/Commercial AI archives")
DEFAULT_REPAIR_LIST = os.path.expanduser("~/ora/data/refusal-repair-list.json")
DEFAULT_REPORT_PATH = os.path.expanduser("~/ora/data/refusal-repair-report.json")

# Raw-archive relocation: cleaned-pair frontmatter records the ORIGINAL
# input path; the historical raw corpus has since moved.
RAW_PREFIX_OLD = "~/Documents/conversations/raw/"
RAW_PREFIX_NEW = "~/Documents/Raw Chat Archive/raw/"


# ---------------------------------------------------------------------------
# Cleaned-pair file surgery helpers
# ---------------------------------------------------------------------------

_FM_LINE_RE = re.compile(r"^(?P<key>[\w ]+):\s*(?P<value>.*)$")


def split_cleaned_pair_file(text: str) -> tuple[list[str], str]:
    """Split a cleaned-pair file into (frontmatter lines, body).

    Frontmatter lines exclude the `---` fences. Raises ValueError on a
    file without a frontmatter block.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("no YAML frontmatter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("unterminated YAML frontmatter")
    return lines[1:end], "\n".join(lines[end + 1:])


def frontmatter_value(fm_lines: list[str], key: str) -> str:
    """Return the (unquoted) value of `key` from frontmatter lines."""
    prefix = f"{key}:"
    for line in fm_lines:
        if line.startswith(prefix):
            v = line[len(prefix):].strip()
            if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
                v = v[1:-1].replace("''", "'")
            return v
    return ""


_SECTION_RE = re.compile(
    r"### User input\n(?P<user>.*?)"
    r"(?=#### Pasted segments|### Assistant response)"
    r"(?:#### Pasted segments\n.*?(?=### Assistant response))?"
    r"### Assistant response\n(?P<ai>.*?)"
    r"(?=#### Engagement strip log|\Z)",
    re.DOTALL,
)


def extract_exchange_sides(body: str) -> tuple[str, str]:
    """Return (user_input_text, assistant_response_text) content sections
    from a cleaned-pair body. Empty strings if the shape is unexpected."""
    m = _SECTION_RE.search(body)
    if not m:
        return "", ""
    return m.group("user").strip(), m.group("ai").strip()


def signature_hits(text: str) -> list[str]:
    low = (text or "").lower()
    return [s for s in REFUSAL_SIGNATURES if s in low]


def resolve_raw_path(source_chat: str) -> Optional[str]:
    """Resolve a frontmatter source_chat to an existing file, applying
    the Raw Chat Archive relocation if needed. None if unresolvable."""
    if not source_chat:
        return None
    p = Path(os.path.expanduser(source_chat))
    if p.is_file():
        return str(p)
    if source_chat.startswith(RAW_PREFIX_OLD):
        moved = RAW_PREFIX_NEW + source_chat[len(RAW_PREFIX_OLD):]
        p2 = Path(os.path.expanduser(moved))
        if p2.is_file():
            return str(p2)
    return None


# ---------------------------------------------------------------------------
# Scan phase
# ---------------------------------------------------------------------------


def scan_archive(archive_dir: str = DEFAULT_ARCHIVE_DIR,
                 progress: bool = True) -> dict:
    """Identify damaged cleaned-pair files. Returns the repair-list dict.

    A file is damaged when a content side carries a refusal signature
    that the corresponding RAW side does not carry (retroactive
    immunity rule). Files whose raw source cannot be located are
    reported separately — they cannot be repaired mechanically.
    """
    archive = Path(archive_dir).expanduser()
    damaged: list[dict[str, Any]] = []
    raw_missing: list[dict[str, Any]] = []
    legit = 0
    scanned = 0
    raw_pair_cache: dict[str, dict[int, tuple[str, str]]] = {}

    def _raw_sides(raw_path: str, pair_num: int) -> Optional[tuple[str, str]]:
        if raw_path not in raw_pair_cache:
            try:
                chat = parse_raw_chat_file(raw_path)
                raw_pair_cache[raw_path] = {
                    p.pair_num: (p.user_content or "", p.assistant_content or "")
                    for p in chat.to_pairs()
                }
            except Exception:
                raw_pair_cache[raw_path] = {}
        return raw_pair_cache[raw_path].get(pair_num)

    for path in sorted(archive.glob("*.md")):
        scanned += 1
        if progress and scanned % 5000 == 0:
            print(f"[scan] {scanned} files...", file=sys.stderr, flush=True)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # Cheap pre-filter before any parsing.
        low = text.lower()
        if not any(s in low for s in REFUSAL_SIGNATURES):
            continue
        try:
            fm, body = split_cleaned_pair_file(text)
        except ValueError:
            continue
        user_side, ai_side = extract_exchange_sides(body)
        user_hits = signature_hits(user_side)
        ai_hits   = signature_hits(ai_side)
        if not user_hits and not ai_hits:
            continue  # signature only in Context/annotations — not content damage

        source_chat = frontmatter_value(fm, "source_chat")
        pair_num    = int(frontmatter_value(fm, "source_pair_num") or 0)
        platform    = frontmatter_value(fm, "source_platform") or "unknown"
        raw_path    = resolve_raw_path(source_chat)
        record = {
            "file":          str(path),
            "source_chat":   source_chat,
            "raw_path":      raw_path,
            "pair_num":      pair_num,
            "platform":      platform,
            "user_hits":     user_hits,
            "ai_hits":       ai_hits,
        }
        if raw_path is None:
            raw_missing.append(record)
            continue
        sides = _raw_sides(raw_path, pair_num)
        if sides is None:
            record["note"] = "pair not found in raw source"
            raw_missing.append(record)
            continue
        raw_user, raw_ai = sides
        # Retroactive immunity: only a signature ABSENT from the raw
        # side is damage.
        user_damaged = any(s not in raw_user.lower() for s in user_hits)
        ai_damaged   = any(s not in raw_ai.lower() for s in ai_hits)
        if not user_damaged and not ai_damaged:
            legit += 1
            continue
        record["user_damaged"] = user_damaged
        record["ai_damaged"]   = ai_damaged
        damaged.append(record)

    result = {
        "scanned_at":   datetime.now().isoformat(timespec="seconds"),
        "archive_dir":  str(archive),
        "files_scanned": scanned,
        "damaged":      damaged,
        "raw_missing":  raw_missing,
        "legit_signature_files": legit,
    }
    return result


# ---------------------------------------------------------------------------
# Repair phase
# ---------------------------------------------------------------------------

_TOPIC_SENTENCE_RE = re.compile(
    r"Topic keywords for this pair: [^.]*\."
)


def build_exchange_block(cleaned: CleanedPair) -> str:
    """Compose the `## Exchange` block exactly as writer.build_body does."""
    parts: list[str] = ["## Exchange\n"]
    parts.append("### User input\n")
    parts.append(cleaned.cleaned_user_input.strip() + "\n")
    paste_block = _format_pasted_segment_annotations(cleaned)
    if paste_block:
        parts.append(paste_block)
    parts.append("### Assistant response\n")
    parts.append(cleaned.cleaned_ai_response.strip() + "\n")
    strip_block = _format_engagement_strip_log(cleaned)
    if strip_block:
        parts.append(strip_block)
    return "\n".join(parts)


def rewrite_cleaned_pair_file(path: str, cleaned: CleanedPair,
                              processing_model: str) -> None:
    """Surgically replace the Exchange block + refresh metadata in place.

    Preserves: filename, frontmatter identity fields, thread links,
    Session context. Regenerates: Exchange block, pair-topic keyword
    sentence, processing_model / processed_at / date modified.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    fm, body = split_cleaned_pair_file(text)

    # Frontmatter refresh.
    now = datetime.now()
    new_fm: list[str] = []
    for line in fm:
        if line.startswith("processing_model:"):
            new_fm.append(f"processing_model: {processing_model}")
        elif line.startswith("processed_at:"):
            new_fm.append(f"processed_at: {now.strftime('%Y-%m-%dT%H:%M:%S')}")
        elif line.startswith("date modified:"):
            new_fm.append(f"date modified: {now.strftime('%Y-%m-%d')}")
        else:
            new_fm.append(line)

    # Body: keep everything before `## Exchange`, replace the rest.
    idx = body.find("## Exchange")
    if idx < 0:
        raise ValueError("no Exchange block")
    head = body[:idx]

    # Regenerate the pair-topic keyword sentence in the preserved head.
    new_kw = extract_keywords(cleaned.cleaned_user_input or "", max_n=5)
    if new_kw:
        head = _TOPIC_SENTENCE_RE.sub(
            f"Topic keywords for this pair: {', '.join(new_kw)}.", head, count=1,
        )

    new_body = head + build_exchange_block(cleaned)
    p.write_text("---\n" + "\n".join(new_fm) + "\n---\n" + new_body,
                 encoding="utf-8")


def repair_damaged(repair_list: dict,
                   backend: str = BACKEND_CLAUDE_CLI,
                   max_workers: int = CLI_RECOMMENDED_MAX_WORKERS,
                   limit: Optional[int] = None,
                   vault_index_path: str = INDEX_DEFAULT,
                   progress: bool = True) -> dict:
    """Re-clean and rewrite every damaged file in the repair list."""
    client = build_client(backend)
    try:
        vault_index = load_index(vault_index_path)
    except Exception:
        vault_index = {"entries": []}

    entries = list(repair_list.get("damaged", []))
    if limit:
        entries = entries[:limit]

    lock = threading.Lock()
    stats = {"repaired": 0, "errors": 0, "still_flagged": 0}
    errors: list[dict] = []
    repaired_files: list[str] = []
    affected_sessions: set[str] = set()
    raw_chat_cache: dict[str, Any] = {}
    counter = {"done": 0}
    start = time.monotonic()

    def _repair_one(entry: dict) -> tuple[dict, str, str]:
        raw_path = entry["raw_path"]
        with lock:
            chat = raw_chat_cache.get(raw_path)
        if chat is None:
            chat = parse_raw_chat_file(raw_path)
            with lock:
                raw_chat_cache[raw_path] = chat
        pair = next((p for p in chat.to_pairs()
                     if p.pair_num == entry["pair_num"]), None)
        if pair is None:
            return entry, "", "pair not found in raw source"
        cleaned = clean_pair(
            pair,
            vault_index=vault_index,
            anthropic_client=client,
            source_path=raw_path,
            source_platform=entry.get("platform", "unknown"),
        )
        if cleaned.errors:
            return entry, "", "; ".join(cleaned.errors)[:300]
        model_label = f"{backend}"
        if cleaned.user_record and cleaned.user_record.route:
            model_label = f"{backend}:{cleaned.user_record.route.tier}"
        rewrite_cleaned_pair_file(entry["file"], cleaned, model_label)
        # Post-repair verification: content sides must be signature-free
        # relative to raw (same immunity rule as the scan).
        new_text = Path(entry["file"]).read_text(encoding="utf-8")
        _, new_body = split_cleaned_pair_file(new_text)
        u, a = extract_exchange_sides(new_body)
        residual = ""
        raw_low = ((pair.user_content or "") + (pair.assistant_content or "")).lower()
        for s in signature_hits(u) + signature_hits(a):
            if s not in raw_low:
                residual = s
                break
        return entry, residual, ""

    def _record(entry: dict, residual: str, error: str) -> None:
        with lock:
            counter["done"] += 1
            if error:
                stats["errors"] += 1
                errors.append({"file": entry["file"], "error": error})
            else:
                stats["repaired"] += 1
                repaired_files.append(entry["file"])
                affected_sessions.add(entry["source_chat"])
                if residual:
                    stats["still_flagged"] += 1
            if progress and counter["done"] % 25 == 0:
                el = time.monotonic() - start
                print(f"[repair] {counter['done']}/{len(entries)} "
                      f"({el:.0f}s) repaired={stats['repaired']} "
                      f"errors={stats['errors']}",
                      file=sys.stderr, flush=True)

    if max_workers <= 1:
        for e in entries:
            entry, residual, err = _repair_one(e)
            _record(entry, residual, err)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_repair_one, e) for e in entries]
            for fut in as_completed(futures):
                try:
                    entry, residual, err = fut.result()
                except Exception as ex:  # never lose the run to one file
                    entry, residual, err = {"file": "?"}, "", f"exception: {ex}"
                _record(entry, residual, err)

    report = {
        "repaired_at":       datetime.now().isoformat(timespec="seconds"),
        "backend":           backend,
        "entries_attempted": len(entries),
        **stats,
        "errors_detail":     errors[:50],
        "repaired_files":    repaired_files,
        "affected_sessions": sorted(affected_sessions),
        "duration_secs":     time.monotonic() - start,
        "client_stats":      vars(client.stats()),
    }
    return report


# ---------------------------------------------------------------------------
# Chunk-layer fix (Layers 3–4 for repaired pairs)
# ---------------------------------------------------------------------------


def fix_chunks(report_path: str = DEFAULT_REPORT_PATH,
               archive_dir: str = DEFAULT_ARCHIVE_DIR,
               progress: bool = True) -> dict:
    """Regenerate chunks + ChromaDB records for repaired pairs.

    The path2 manifest was lost with the raw-archive relocation, so this
    reconstructs it: every session in the archive is marked completed
    EXCEPT the repaired ones, whose stale chunk files are deleted (their
    paths recovered from ChromaDB metadata under the deterministic
    `session-<id>-pair-<n>` ids) before path2 re-emits them. ChromaDB
    records heal by upsert under the same ids.
    """
    import chromadb
    from orchestrator.embedding import get_or_create_collection
    from orchestrator.historical.chain_detector import derive_session_id
    from orchestrator.historical.cleaned_pair_reader import load_cleaned_pair
    from orchestrator.historical.path2_cli import (
        DEFAULT_MANIFEST_PATH as PATH2_MANIFEST,
        load_manifest as load_p2_manifest,
        run_chain_detection,
        run_chunk_emission,
        save_manifest as save_p2_manifest,
    )
    from orchestrator.historical.path2_orchestrator import (
        group_cleaned_pairs_by_session,
    )

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    affected = set(report.get("affected_sessions", []))
    if not affected:
        return {"status": "no affected sessions"}

    # Group the whole archive by session (source_chat).
    files = [str(p) for p in Path(archive_dir).expanduser().glob("*.md")]
    if progress:
        print(f"[fix-chunks] grouping {len(files):,} cleaned pairs by "
              f"session...", file=sys.stderr, flush=True)
    sessions = group_cleaned_pairs_by_session(files)

    # Reconstruct the path2 manifest if it lacks completed sessions:
    # everything completed except the affected set.
    manifest = load_p2_manifest(PATH2_MANIFEST)
    completed = manifest.setdefault("completed_sessions", {})
    reconstructed = 0
    if not completed:
        stamp = datetime.now().isoformat(timespec="seconds")
        for source in sessions:
            if source in affected:
                continue
            completed[source] = {
                "completed_at": stamp,
                "session_id":   derive_session_id(source),
                "reconstructed": True,
            }
            reconstructed += 1
        manifest["reconstructed_at"] = stamp
    else:
        for source in affected:
            completed.pop(source, None)
    save_p2_manifest(manifest, PATH2_MANIFEST)
    if progress:
        print(f"[fix-chunks] manifest: {len(completed):,} completed "
              f"({reconstructed:,} reconstructed), {len(affected)} affected "
              f"sessions pending re-emission", file=sys.stderr, flush=True)

    # Delete stale chunk files for affected sessions (paths recovered
    # from ChromaDB metadata under deterministic ids).
    client = chromadb.PersistentClient(
        path="/Users/oracle/ora/chromadb")
    col = get_or_create_collection(client, "conversations")
    stale_deleted = 0
    ids_batch: list[str] = []
    for source in affected:
        sid = derive_session_id(source)
        for path in sessions.get(source, []):
            try:
                cp = load_cleaned_pair(path)
                ids_batch.append(f"session-{sid}-pair-{cp.source_pair_num:03d}")
            except Exception:
                continue
    for i in range(0, len(ids_batch), 200):
        got = col.get(ids=ids_batch[i:i + 200], include=["metadatas"])
        for meta in (got.get("metadatas") or []):
            cpath = (meta or {}).get("chunk_path", "")
            if cpath and os.path.isfile(cpath):
                os.unlink(cpath)
                stale_deleted += 1
    if progress:
        print(f"[fix-chunks] deleted {stale_deleted} stale chunk files",
              file=sys.stderr, flush=True)

    # Re-run path2: chain detection (deterministic) + emission of the
    # affected sessions only (everything else is manifest-complete).
    detection = run_chain_detection(cleaned_pair_dir=archive_dir,
                                    progress_to_stderr=progress)
    emission = run_chunk_emission(detection["sessions_to_paths"],
                                  progress_to_stderr=progress)
    return {
        "affected_sessions":    len(affected),
        "manifest_reconstructed": reconstructed,
        "stale_chunks_deleted": stale_deleted,
        "emission":             emission,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan for + repair Refusal Leak damage in the "
                    "cleaned-pair archive.",
    )
    parser.add_argument("--scan", action="store_true",
                        help="Identify damaged files; write the repair list")
    parser.add_argument("--repair", action="store_true",
                        help="Repair files from the repair list")
    parser.add_argument("--fix-chunks", action="store_true",
                        help="Regenerate chunks + ChromaDB for repaired pairs")
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--repair-list", default=DEFAULT_REPAIR_LIST)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--backend", choices=list(BACKEND_CHOICES),
                        default=BACKEND_CLAUDE_CLI)
    parser.add_argument("--max-workers", type=int,
                        default=CLI_RECOMMENDED_MAX_WORKERS)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if not args.scan and not args.repair and not args.fix_chunks:
        parser.error("pass --scan, --repair, and/or --fix-chunks")

    if args.scan:
        result = scan_archive(args.archive_dir)
        Path(args.repair_list).parent.mkdir(parents=True, exist_ok=True)
        Path(args.repair_list).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        print(json.dumps({
            "files_scanned":  result["files_scanned"],
            "damaged":        len(result["damaged"]),
            "raw_missing":    len(result["raw_missing"]),
            "legit_signature_files": result["legit_signature_files"],
            "repair_list":    args.repair_list,
        }, indent=2))

    if args.repair:
        repair_list = json.loads(Path(args.repair_list).read_text(encoding="utf-8"))
        report = repair_damaged(
            repair_list,
            backend=args.backend,
            max_workers=args.max_workers,
            limit=args.limit,
        )
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        summary = {k: v for k, v in report.items()
                   if k not in ("repaired_files", "affected_sessions",
                                "errors_detail", "client_stats")}
        summary["report"] = args.report
        print(json.dumps(summary, indent=2))

    if args.fix_chunks:
        result = fix_chunks(args.report, args.archive_dir)
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "scan_archive",
    "repair_damaged",
    "fix_chunks",
    "rewrite_cleaned_pair_file",
    "build_exchange_block",
    "extract_exchange_sides",
    "split_cleaned_pair_file",
    "resolve_raw_path",
    "main",
]
