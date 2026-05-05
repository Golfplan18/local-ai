"""Mark privacy on historical conversation pairs.

Two-pass detection:
  Pass A — keyword scan (dating apps + family names + user-supplied list)
  Pass B — Haiku LLM scan on each session's title + opening pair to catch
           non-famous-individual conversations the keywords miss

Propagation:
  - Within a thread (same thread_id within a session): always propagate
  - Across a chain: propagate to whole chain ONLY if ≥ MIN_PRIVATE_FRACTION_OF_CHAIN
    of its pairs were initially detected as private. Avoids sweeping the
    user's giant "framework" chain just because one tangential pair
    mentioned a date.

Tags are applied to FIVE layers per affected pair:
  1. Cleaned-pair file YAML (`tags` += "private")
  2. Conversation chunk file YAML in `~/Documents/conversations/`
     (sets `tag: private`, adds to `tags`)
  3. ChromaDB conversation record metadata (`tag_private: True`,
     `tag: "private"`, `tags: ["private"]`)
  4. Atomic engram notes with matching source_chat + source_pair_num
     (`tags` += "private")
  5. Source notes (News/Opinion/Resources) with matching source —
     same as 4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.chain_detector import (
    derive_session_id,
    load_chain_index,
    CHAIN_INDEX_DEFAULT,
)
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ARCHIVE_DIR     = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_CONVERSATIONS_DIR = "/Users/oracle/Documents/conversations"
DEFAULT_VAULT_ROOT      = "/Users/oracle/Documents/vault"
DEFAULT_CHROMADB_PATH   = "/Users/oracle/ora/chromadb"
DEFAULT_MANIFEST_PATH   = "/Users/oracle/ora/data/privacy-manifest.json"
DEFAULT_REPORT_PATH     = "/Users/oracle/ora/data/privacy-report.json"

# Propagate chain → all-private when this fraction of the chain's
# detected pairs are private. Conservative — avoids sweeping a 500-
# session framework chain because of one stray dating mention.
MIN_PRIVATE_FRACTION_OF_CHAIN = 0.50

# Skip pair-level keyword scan on pairs below this length (no real
# content to evaluate).
MIN_PAIR_CHARS_FOR_SCAN = 50


# ---------------------------------------------------------------------------
# Pass A — keyword detection
# ---------------------------------------------------------------------------


# Whole-word keywords that mark a pair as private. Case-insensitive.
# IMPORTANT: these must be discriminative — false positives create a
# privacy LEAK in the wrong direction (marking too much as private also
# hides real content from RAG). Use exact app names + the specific
# family names the user provided.
_KEYWORD_TRIGGERS = {
    # Dating apps
    "dating-app": [
        r"\bhinge\b", r"\bbumble\b", r"\btinder\b", r"\bokcupid\b",
        r"\bmatch\.com\b", r"\bmatch\s*com\b",
        r"\beharmony\b", r"\bcoffee\s+meets\s+bagel\b",
        r"\bplenty\s+of\s+fish\b", r"\bpof\b",
        r"\bdating\s+app\b", r"\bdating\s+profile\b",
        r"\bfirst\s+date\b", r"\bonline\s+dating\b",
    ],
    # Specific family names supplied by user
    "family-james": [r"\bJames\b"],
    "family-michelle": [r"\bMichelle\b"],
    "family-larry": [r"\bLarry\s+Roberts\b", r"\bLarry\b(?=.*Roberts)"],
    "family-audrey": [r"\bAudrey\s+Roberts\b", r"\bAudrey\b(?=.*Roberts)"],
    # Family relationship language (catches "my son", "my ex-wife"
    # without specific names)
    "family-relationship": [
        r"\bmy\s+son\b", r"\bmy\s+ex[-\s]?wife\b",
        r"\bmy\s+(?:mom|mother|dad|father)\b",
        r"\bmy\s+parents\b",
    ],
}

# Compile patterns (case-insensitive).
_COMPILED_TRIGGERS: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in pats]
    for cat, pats in _KEYWORD_TRIGGERS.items()
}


# Discriminative-name caveat: "James" as a bare word matches a lot of
# things (James Madison, books, characters, actors). Apply only when
# the surrounding context suggests personal reference. Heuristic:
# require "my James" or "James (" or possessive use, OR rely on LLM
# Pass B for bare mentions.
_FAMILY_NAME_FAMILIAR_RE = {
    "james":   re.compile(r"\b(?:my\s+(?:son\s+)?James|James['']s|James\s+(?:and|is|was|came|said))\b", re.IGNORECASE),
    "michelle": re.compile(r"\b(?:my\s+(?:ex[-\s]?wife\s+)?Michelle|Michelle['']s|Michelle\s+(?:and|is|was|came|said))\b", re.IGNORECASE),
}

# Fiction-context exclusion. The user's American Jesus narrative includes
# a character James Zebedee. Any pair whose content / filename mentions
# AJ terms is treated as fiction and the family-name trigger is skipped.
_FICTION_CONTEXT_RE = re.compile(
    r"\b(?:American\s+Jesus|Hayzeus|Diklis\s+Chump|Zebedee|"
    r"Peter\s+Stone|Jerry\s+Farwright|Thomas\s+Reynolds|Joanna\s+Riviera|"
    r"Blackwell|chapter\s+\d+|story\s+beat|character\s+(?:foundation|"
    r"initiation|profile|outline|framework))\b",
    re.IGNORECASE,
)


def keyword_scan(text: str, source_filename: str = "") -> list[str]:
    """Return list of trigger labels matching this text. Empty list if
    nothing matched. Searches both content and filename."""
    haystack = f"{source_filename}\n{text}"
    in_fiction_context = bool(_FICTION_CONTEXT_RE.search(haystack))

    hits: list[str] = []
    for category, patterns in _COMPILED_TRIGGERS.items():
        # Family-name-only categories need familiar-context check, AND
        # are suppressed in fiction context (James Zebedee character
        # would otherwise sweep the entire American Jesus archive).
        if category == "family-james":
            if in_fiction_context:
                continue
            if _FAMILY_NAME_FAMILIAR_RE["james"].search(haystack):
                hits.append(category)
            continue
        if category == "family-michelle":
            if in_fiction_context:
                continue
            if _FAMILY_NAME_FAMILIAR_RE["michelle"].search(haystack):
                hits.append(category)
            continue
        for pat in patterns:
            if pat.search(haystack):
                hits.append(category)
                break
    return hits


# ---------------------------------------------------------------------------
# Pass B — LLM session-level scan
# ---------------------------------------------------------------------------


_PRIVACY_SYSTEM = """\
You decide whether a conversation is PRIVATE.

A conversation is PRIVATE if it primarily discusses any of:
- A specific non-famous individual person (a date, a friend, a colleague, a family member)
- Dating app activity or romantic interests
- The user's family members (son, ex-wife, parents, siblings)
- Mental health, therapy, personal medical matters

A conversation is PUBLIC if it primarily discusses:
- Famous public figures (politicians, celebrities, historical figures)
- News events, current events, political analysis
- Technical work, code, software, frameworks, system design
- Philosophy, theology, abstract concepts (NOT involving the user's personal life)
- Fiction projects with invented characters (American Jesus, Diklis Chump, Hayzeus, etc.)
- Public commentary on books, movies, ideas

Reply with ONE word only: PRIVATE or PUBLIC. No explanation."""


def llm_session_scan(
    title: str,
    opening_text: str,
    *,
    client: AnthropicClient,
) -> tuple[bool, int, int, float, str]:
    """Send a session's title + opening content to Haiku, return
    (is_private, in_tok, out_tok, cost, error)."""
    user_msg = (
        f"Filename: {title}\n\n"
        f"Opening conversation:\n<<<\n{opening_text[:2000]}\n>>>\n\n"
        f"Verdict:"
    )
    result = client.call(
        system=_PRIVACY_SYSTEM,
        user=user_msg,
        model="claude-haiku-4-5",
        max_tokens=8,
        temperature=0.0,
    )
    if result.error:
        return False, result.input_tokens, result.output_tokens, result.cost_usd, result.error
    label = result.text.strip().upper()
    label = re.sub(r"[^A-Z]", "", label)
    is_private = label.startswith("PRIVATE")
    return is_private, result.input_tokens, result.output_tokens, result.cost_usd, ""


# ---------------------------------------------------------------------------
# Detection orchestration
# ---------------------------------------------------------------------------


@dataclass
class PairDetection:
    """Privacy detection result for one cleaned-pair."""
    file_path:        str
    source_chat:      str
    source_pair_num:  int
    thread_id:        str
    chain_id:         str
    is_private:       bool = False
    triggers:         list[str] = field(default_factory=list)
    detected_by:      str = ""   # "keyword" | "llm-session" | "thread-prop" | "chain-prop"


def _build_session_groups(
    archive_dir: str,
    chain_lookup: dict,
) -> dict[str, list[CleanedPairFile]]:
    """Walk the archive and group cleaned-pair files by source_chat."""
    groups: dict[str, list[CleanedPairFile]] = defaultdict(list)
    for f in Path(archive_dir).glob("*.md"):
        try:
            cp = load_cleaned_pair(f)
            groups[cp.source_chat].append(cp)
        except Exception:
            continue
    for src in groups:
        groups[src].sort(key=lambda c: c.source_pair_num)
    return groups


def detect_privacy(
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
    *,
    chain_index_path: str = CHAIN_INDEX_DEFAULT,
    max_workers:      int = 8,
    progress_to_stderr: bool = True,
    skip_llm_scan:    bool = False,
) -> tuple[dict[str, PairDetection], dict]:
    """Run Pass A keyword + Pass B LLM session scan. Returns:
        (detections by uid, summary stats)
    where uid = f"{source_chat}#{source_pair_num}".

    Detections are pre-propagation. Caller propagates via
    `propagate_within_threads` and `propagate_within_chains`."""
    start = time.monotonic()
    chain_lookup = load_chain_index(chain_index_path)
    session_to_chain = chain_lookup.get("session_to_chain", {})

    if progress_to_stderr:
        print("[privacy] enumerating pairs…", file=sys.stderr, flush=True)
    groups = _build_session_groups(archive_dir, chain_lookup)
    total_pairs = sum(len(v) for v in groups.values())
    if progress_to_stderr:
        print(f"[privacy] {len(groups):,} sessions / {total_pairs:,} pairs",
              file=sys.stderr, flush=True)

    # Build per-pair detections initialized empty.
    detections: dict[str, PairDetection] = {}
    for source_chat, cps in groups.items():
        sid = derive_session_id(source_chat)
        chain_id = session_to_chain.get(sid, "")
        for cp in cps:
            uid = f"{source_chat}#{cp.source_pair_num}"
            detections[uid] = PairDetection(
                file_path=cp.file_path,
                source_chat=source_chat,
                source_pair_num=cp.source_pair_num,
                thread_id=cp.thread_id,
                chain_id=chain_id,
            )

    # Pass A: keyword scan, per pair.
    if progress_to_stderr:
        print("[privacy] Pass A — keyword scan", file=sys.stderr, flush=True)
    a_hits = 0
    for source_chat, cps in groups.items():
        for cp in cps:
            text = (cp.cleaned_user_input or "") + "\n" + (cp.cleaned_ai_response or "")
            if len(text) < MIN_PAIR_CHARS_FOR_SCAN:
                continue
            triggers = keyword_scan(text, source_filename=Path(source_chat).name)
            if triggers:
                uid = f"{source_chat}#{cp.source_pair_num}"
                d = detections[uid]
                d.is_private = True
                d.triggers = triggers
                d.detected_by = "keyword"
                a_hits += 1
    if progress_to_stderr:
        print(f"[privacy]   Pass A: {a_hits:,} pairs flagged "
              f"({a_hits/max(1,total_pairs)*100:.1f}%)",
              file=sys.stderr, flush=True)

    # Pass B: LLM session scan. Only on sessions with NO Pass-A hit
    # (because if Pass A caught any pair we'll handle it via propagation).
    if not skip_llm_scan:
        if progress_to_stderr:
            print("[privacy] Pass B — LLM session scan", file=sys.stderr,
                  flush=True)
        client = AnthropicClient()

        # Sessions to scan: those with no Pass-A hits AT ALL.
        sessions_with_a_hit: set[str] = set()
        for d in detections.values():
            if d.is_private:
                sessions_with_a_hit.add(d.source_chat)

        sessions_to_scan = [src for src in groups if src not in sessions_with_a_hit]
        if progress_to_stderr:
            print(f"[privacy]   {len(sessions_to_scan):,} sessions to LLM-scan "
                  f"(skipping {len(sessions_with_a_hit):,} already flagged)",
                  file=sys.stderr, flush=True)

        b_hits = 0
        b_cost = 0.0
        b_in = 0
        b_out = 0

        def _scan_one(src: str) -> tuple[str, bool, int, int, float, str]:
            cps = groups[src]
            opening = (cps[0].cleaned_user_input or "")[:1000] + "\n" \
                       + (cps[0].cleaned_ai_response or "")[:1000]
            title = Path(src).stem
            return (src,) + llm_session_scan(title, opening, client=client)

        counter = {"done": 0}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_scan_one, src): src for src in sessions_to_scan}
            for fut in as_completed(futures):
                src, is_priv, ti, to, cost, err = fut.result()
                counter["done"] += 1
                b_in += ti
                b_out += to
                b_cost += cost
                if is_priv:
                    b_hits += 1
                    # Mark ALL pairs in this session as private.
                    for cp in groups[src]:
                        uid = f"{src}#{cp.source_pair_num}"
                        d = detections[uid]
                        d.is_private = True
                        d.triggers = ["llm-session-scan"]
                        d.detected_by = "llm-session"
                if progress_to_stderr and counter["done"] % 200 == 0:
                    print(f"[privacy]   {counter['done']:,}/{len(sessions_to_scan):,} "
                          f"scanned ({b_hits:,} private so far) ${b_cost:.2f}",
                          file=sys.stderr, flush=True)

        if progress_to_stderr:
            print(f"[privacy]   Pass B: {b_hits:,} sessions flagged private, "
                  f"${b_cost:.2f}", file=sys.stderr, flush=True)
    else:
        b_hits = 0
        b_cost = 0.0
        b_in = b_out = 0

    summary = {
        "sessions_total": len(groups),
        "pairs_total":    total_pairs,
        "pass_a_hits":    a_hits,
        "pass_b_session_hits": b_hits,
        "pass_b_cost":    b_cost,
        "pass_b_input_tokens":  b_in,
        "pass_b_output_tokens": b_out,
        "duration_secs":  time.monotonic() - start,
    }
    return detections, summary


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------


def propagate_within_threads(
    detections: dict[str, PairDetection],
) -> int:
    """For each thread (same thread_id), if ANY pair is private, mark
    all pairs in that thread as private. Returns the number of newly-
    flagged pairs."""
    threads_with_private: set[str] = set()
    for d in detections.values():
        if d.is_private and d.thread_id:
            threads_with_private.add(d.thread_id)
    newly_flagged = 0
    for d in detections.values():
        if not d.is_private and d.thread_id in threads_with_private:
            d.is_private = True
            d.detected_by = "thread-prop"
            newly_flagged += 1
    return newly_flagged


def propagate_within_chains(
    detections: dict[str, PairDetection],
    *,
    min_fraction: float = MIN_PRIVATE_FRACTION_OF_CHAIN,
) -> tuple[int, list[str]]:
    """For each chain, compute fraction of pairs marked private. If
    fraction ≥ min_fraction, mark ALL pairs in the chain as private.
    Returns (newly_flagged_count, chain_ids_propagated)."""
    by_chain_total: Counter[str] = Counter()
    by_chain_private: Counter[str] = Counter()
    for d in detections.values():
        if not d.chain_id:
            continue
        by_chain_total[d.chain_id] += 1
        if d.is_private:
            by_chain_private[d.chain_id] += 1

    propagated_chains: list[str] = []
    for cid, total in by_chain_total.items():
        if total == 0:
            continue
        frac = by_chain_private[cid] / total
        if frac >= min_fraction:
            propagated_chains.append(cid)

    propagated_set = set(propagated_chains)
    newly_flagged = 0
    for d in detections.values():
        if not d.is_private and d.chain_id in propagated_set:
            d.is_private = True
            d.detected_by = "chain-prop"
            newly_flagged += 1
    return newly_flagged, propagated_chains


# ---------------------------------------------------------------------------
# Tag application — five layers
# ---------------------------------------------------------------------------


_YAML_TAGS_RE = re.compile(r"^tags:\s*\n((?:^  - .*\n)*)", re.MULTILINE)
_YAML_TAGS_INLINE_RE = re.compile(r"^tags:\s*\[(.*?)\]\s*$", re.MULTILINE)


def _add_private_tag_to_yaml(text: str) -> str:
    """Insert `- private` into the YAML's `tags:` list if not already
    present. Handles both block-style and inline-list formats."""
    # Block style:
    m = _YAML_TAGS_RE.search(text)
    if m:
        existing = m.group(1)
        if re.search(r"^  - private$", existing, re.MULTILINE):
            return text
        new_block = "tags:\n  - private\n" + existing
        return text[:m.start()] + new_block + text[m.end():]
    # Inline list:
    m = _YAML_TAGS_INLINE_RE.search(text)
    if m:
        contents = m.group(1).strip()
        items = [s.strip().strip("'\"") for s in contents.split(",") if s.strip()]
        if "private" in items:
            return text
        items.insert(0, "private")
        new_line = f"tags: [{', '.join(items)}]"
        return text[:m.start()] + new_line + text[m.end():]
    # No tags line — insert one before the YAML closer.
    closer_m = re.search(r"^---\s*$", text[3:], re.MULTILINE)
    if closer_m:
        insert_at = 3 + closer_m.start()
        return text[:insert_at] + "tags:\n  - private\n" + text[insert_at:]
    return text


def _tag_cleaned_pair_file(file_path: str) -> bool:
    p = Path(file_path)
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    new_text = _add_private_tag_to_yaml(text)
    if new_text == text:
        return False
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(p)
    return True


# ---------------------------------------------------------------------------
# Find downstream notes (chunks, atomics, source notes) for a private pair
# ---------------------------------------------------------------------------


def _scan_yaml_for_match(
    file_path: Path,
    source_chat: str,
    pair_num: int,
) -> bool:
    """Quick test: does this vault file's YAML reference the given
    (source_chat, pair_num)?"""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return False
    # Cheap substring scan first to avoid full YAML parse on every file.
    if str(pair_num) not in text:
        return False
    # Match on source_chat (it's a path-like string in YAML)
    sc_norm = source_chat.replace(os.path.expanduser("~/"), "~/")
    if sc_norm not in text and source_chat not in text:
        return False
    # Confirm pair_num matches in YAML.
    pair_m = re.search(r"^source_pair_num:\s*(\d+)\s*$", text, re.MULTILINE)
    if not pair_m or int(pair_m.group(1)) != pair_num:
        return False
    return True


def _build_pair_to_files_index(
    conversations_dir: str,
    vault_root: str,
) -> dict[tuple[str, int], dict[str, list[str]]]:
    """Walk chunks + atomic + source notes ONCE and index by
    (source_chat, pair_num) → {layer: [file_path, ...]}.

    Pre-building this index avoids O(N×M) scans during tagging.
    Returns dict mapping (source_chat_normalized, pair_num) →
        {"chunk": [...], "atomic": [...], "source": [...]}.
    """
    idx: dict[tuple[str, int], dict[str, list[str]]] = defaultdict(
        lambda: {"chunk": [], "atomic": [], "source": []}
    )
    sc_re = re.compile(r"^source_chat:\s*(.+)$", re.MULTILINE)
    pn_re = re.compile(r"^source_pair_num:\s*(\d+)\s*$", re.MULTILINE)

    def _add(file_path: Path, layer: str):
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            return
        sc_m = sc_re.search(text)
        pn_m = pn_re.search(text)
        if not sc_m or not pn_m:
            return
        sc = sc_m.group(1).strip().strip("'\"")
        sc = sc.replace("~/", os.path.expanduser("~/"))
        try:
            pn = int(pn_m.group(1))
        except ValueError:
            return
        idx[(sc, pn)][layer].append(str(file_path))

    # Conversation chunks
    for f in Path(conversations_dir).glob("*.md"):
        _add(f, "chunk")
    # Atomic engram notes
    atomic_root = Path(vault_root) / "Engrams" / "Historical Atomics"
    for f in atomic_root.rglob("*.md"):
        _add(f, "atomic")
    # Source notes
    for sub in ("News", "Opinion", "Resources"):
        src_root = Path(vault_root) / "Sources" / sub
        for f in src_root.rglob("*.md"):
            _add(f, "source")

    return idx


# ---------------------------------------------------------------------------
# ChromaDB metadata update
# ---------------------------------------------------------------------------


def _chunk_id_for(source_chat: str, pair_num: int) -> str:
    """Same chunk_id convention as path2_orchestrator."""
    sid = derive_session_id(source_chat)
    return f"session-{sid}-pair-{pair_num:03d}"


def _update_chromadb_chunks(
    private_pairs: list[tuple[str, int]],
    *,
    chromadb_path: str,
) -> int:
    """For each (source_chat, pair_num) in private_pairs, set
    `tag_private: True`, `tag: 'private'` on its ChromaDB record.
    Returns the number of records updated."""
    import chromadb
    from orchestrator.embedding import get_or_create_collection
    client = chromadb.PersistentClient(path=str(chromadb_path))
    col = get_or_create_collection(client, "conversations")

    chunk_ids = [_chunk_id_for(sc, pn) for sc, pn in private_pairs]
    # Batch fetch in chunks of 1000
    BATCH = 1000
    updated = 0
    for i in range(0, len(chunk_ids), BATCH):
        ids_batch = chunk_ids[i:i + BATCH]
        try:
            existing = col.get(ids=ids_batch, include=["metadatas"])
        except Exception:
            continue
        if not existing["ids"]:
            continue
        new_metas: list[dict] = []
        for old_meta in existing["metadatas"]:
            new_meta = dict(old_meta or {})
            new_meta["tag"]          = "private"
            new_meta["tag_private"]  = True
            new_meta["tags"]         = "private"   # Chroma doesn't accept lists post-hoc cleanly
            new_metas.append(new_meta)
        try:
            col.update(ids=existing["ids"], metadatas=new_metas)
            updated += len(existing["ids"])
        except Exception:
            pass
    return updated


# ---------------------------------------------------------------------------
# Main apply step
# ---------------------------------------------------------------------------


def apply_privacy_tags(
    detections: dict[str, PairDetection],
    *,
    conversations_dir: str = DEFAULT_CONVERSATIONS_DIR,
    vault_root: str = DEFAULT_VAULT_ROOT,
    chromadb_path: str = DEFAULT_CHROMADB_PATH,
    progress_to_stderr: bool = True,
) -> dict:
    """Apply privacy tags at all five layers for every detected-private
    pair. Returns count summary."""
    private = [d for d in detections.values() if d.is_private]
    if progress_to_stderr:
        print(f"[privacy] applying tags to {len(private):,} private pairs…",
              file=sys.stderr, flush=True)

    # Build downstream index ONCE (chunks, atomics, source notes).
    if progress_to_stderr:
        print("[privacy]   building downstream index…", file=sys.stderr,
              flush=True)
    pair_idx = _build_pair_to_files_index(conversations_dir, vault_root)
    if progress_to_stderr:
        print(f"[privacy]   indexed {len(pair_idx):,} (source_chat, pair) keys",
              file=sys.stderr, flush=True)

    counts = {
        "cleaned_pair_files": 0,
        "chunk_files":        0,
        "atomic_notes":       0,
        "source_notes":       0,
        "chromadb_chunks":    0,
    }
    private_keys: list[tuple[str, int]] = []
    for d in private:
        # Layer 1: cleaned-pair file
        if _tag_cleaned_pair_file(d.file_path):
            counts["cleaned_pair_files"] += 1
        # Layers 2 + 4 + 5: lookup downstream files
        sc_resolved = d.source_chat.replace("~/", os.path.expanduser("~/"))
        key = (sc_resolved, d.source_pair_num)
        idx_entry = pair_idx.get(key, {"chunk": [], "atomic": [], "source": []})
        for chunk_path in idx_entry["chunk"]:
            if _tag_cleaned_pair_file(chunk_path):
                counts["chunk_files"] += 1
        for atomic_path in idx_entry["atomic"]:
            if _tag_cleaned_pair_file(atomic_path):
                counts["atomic_notes"] += 1
        for source_path in idx_entry["source"]:
            if _tag_cleaned_pair_file(source_path):
                counts["source_notes"] += 1
        private_keys.append((d.source_chat, d.source_pair_num))

    # Layer 3: ChromaDB metadata update (batched)
    if progress_to_stderr:
        print("[privacy]   updating ChromaDB metadata…", file=sys.stderr,
              flush=True)
    counts["chromadb_chunks"] = _update_chromadb_chunks(
        private_keys, chromadb_path=chromadb_path,
    )
    return counts


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_privacy_tagging(
    archive_dir:        str = DEFAULT_ARCHIVE_DIR,
    *,
    conversations_dir:  str = DEFAULT_CONVERSATIONS_DIR,
    vault_root:         str = DEFAULT_VAULT_ROOT,
    chromadb_path:      str = DEFAULT_CHROMADB_PATH,
    chain_index_path:   str = CHAIN_INDEX_DEFAULT,
    max_workers:        int = 8,
    skip_llm_scan:      bool = False,
    detection_only:     bool = False,
    progress_to_stderr: bool = True,
) -> dict:
    detections, detect_summary = detect_privacy(
        archive_dir,
        chain_index_path=chain_index_path,
        max_workers=max_workers,
        progress_to_stderr=progress_to_stderr,
        skip_llm_scan=skip_llm_scan,
    )

    if progress_to_stderr:
        n_initial = sum(1 for d in detections.values() if d.is_private)
        print(f"[privacy] {n_initial:,} pairs flagged before propagation",
              file=sys.stderr, flush=True)

    thread_added = propagate_within_threads(detections)
    chain_added, chains = propagate_within_chains(detections)
    if progress_to_stderr:
        print(f"[privacy] propagation: +{thread_added:,} via thread, "
              f"+{chain_added:,} via {len(chains)} chains "
              f"(≥{MIN_PRIVATE_FRACTION_OF_CHAIN*100:.0f}% threshold)",
              file=sys.stderr, flush=True)

    n_final = sum(1 for d in detections.values() if d.is_private)
    summary = {
        **detect_summary,
        "pairs_flagged_after_propagation": n_final,
        "thread_propagation_added":  thread_added,
        "chain_propagation_added":   chain_added,
        "chains_propagated":         len(chains),
    }

    if not detection_only:
        apply_counts = apply_privacy_tags(
            detections,
            conversations_dir=conversations_dir,
            vault_root=vault_root,
            chromadb_path=chromadb_path,
            progress_to_stderr=progress_to_stderr,
        )
        summary["applied_counts"] = apply_counts

    # Per-detected-by breakdown
    by_method: Counter[str] = Counter()
    for d in detections.values():
        if d.is_private:
            by_method[d.detected_by] += 1
    summary["by_method"] = dict(by_method)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mark historical conversation pairs as private.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--conversations-dir", default=DEFAULT_CONVERSATIONS_DIR)
    parser.add_argument("--vault-root", default=DEFAULT_VAULT_ROOT)
    parser.add_argument("--chromadb-path", default=DEFAULT_CHROMADB_PATH)
    parser.add_argument("--chain-index", default=CHAIN_INDEX_DEFAULT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--skip-llm-scan", action="store_true",
                          help="Skip Pass B (Haiku LLM session scan)")
    parser.add_argument("--detection-only", action="store_true",
                          help="Detect + propagate but DON'T apply tags")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    summary = run_privacy_tagging(
        archive_dir=args.archive_dir,
        conversations_dir=args.conversations_dir,
        vault_root=args.vault_root,
        chromadb_path=args.chromadb_path,
        chain_index_path=args.chain_index,
        max_workers=args.max_workers,
        skip_llm_scan=args.skip_llm_scan,
        detection_only=args.detection_only,
        progress_to_stderr=not args.quiet,
    )
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "MIN_PRIVATE_FRACTION_OF_CHAIN",
    "PairDetection",
    "keyword_scan",
    "llm_session_scan",
    "detect_privacy",
    "propagate_within_threads",
    "propagate_within_chains",
    "apply_privacy_tags",
    "run_privacy_tagging",
    "main",
]
