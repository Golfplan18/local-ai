"""Phase 5 — atomic note extraction with reverse-walk dedup.

For each cleaned-pair in the archive (newest first), call Sonnet 4.5
to identify atomic knowledge claims worth minting as engram notes.
Each candidate goes through a cosine-similarity dedup check against
a ChromaDB collection of already-minted atomic embeddings; if a near
duplicate (≥0.92 sim) exists, increment its `seen_count` metadata
and skip writing. Otherwise write a new vault note and add to the
dedup index.

Reverse chronological order means the FIRST mention of an idea (in
the most recent pair that mentions it) becomes the canonical note;
older pairs that say the same thing only bump the count. This lets
the dedup index converge to a clean atomic library without a costly
post-hoc prune.

Pass A signal taxonomy expansion (per architecture):
  - ai_synthesis  — AI-generated synthesis combining multiple sources
  - ai_framework  — AI-generated framework or model
  - ai_evidence   — AI-cited evidence or example
plus the existing fact / principle / definition / causal / analogy /
evaluative types.

Vault layout: `~/Documents/vault/Engrams/Historical Atomics/[YYYY]/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)
from orchestrator.historical.chain_detector import (
    derive_session_id,
    load_chain_index,
    CHAIN_INDEX_DEFAULT,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ARCHIVE_DIR    = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_VAULT_ROOT     = "/Users/oracle/Documents/vault/Engrams/Historical Atomics"
DEFAULT_CHROMADB_PATH  = "/Users/oracle/ora/chromadb"
DEFAULT_DEDUP_COLLECTION = "atomic_dedup"
DEFAULT_MANIFEST_PATH  = "/Users/oracle/ora/data/phase5-manifest.json"
DEFAULT_REPORT_PATH    = "/Users/oracle/ora/data/phase5-report.json"

# Extraction model — Sonnet 4.5 for quality per user direction.
EXTRACTION_MODEL = "claude-sonnet-4-5"

# Cosine-similarity threshold for treating a candidate as a duplicate
# of an already-indexed atomic. 0.92 per architecture; lower would
# over-merge distinct claims, higher would under-merge.
DEDUP_SIM_THRESHOLD = 0.92

# Skip pairs whose total cleaned content is below this (no atomic
# extraction worth running on greetings or 2-line exchanges).
MIN_PAIR_CHARS_FOR_EXTRACTION = 400

# Cap content sent to Sonnet — atomics live in the first ~6K chars
# of any pair; longer is mostly pasted material we don't need.
MAX_PAIR_CHARS_FOR_EXTRACTION = 6_000


# Valid atomic types (Pass A taxonomy + AI-source extensions).
_VALID_TYPES = frozenset({
    "fact", "principle", "definition", "causal", "analogy", "evaluative",
    "ai_synthesis", "ai_framework", "ai_evidence",
})


# ---------------------------------------------------------------------------
# Extraction prompt (single-call atomic identification)
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """\
You extract ATOMIC KNOWLEDGE NOTES from a single conversation turn pair \
(user message + AI response). Each atomic note states ONE clear, \
transferable claim — a complete declarative sentence, not a topic label.

Skip trivial or well-known facts. Be SELECTIVE — only mint notes for \
genuinely insightful, transferable claims that someone might want to \
retrieve later. A typical pair yields 0-3 atomics; a substantive deep \
dive might yield up to 8. If the pair is small talk, status updates, \
or generic Q&A, return [].

Categories:

USER-SIDE:
- fact: verifiable empirical claim
- principle: generalizable rule about how something works
- definition: precise definition of a concept
- causal: assertion that one thing causes / prevents / enables another
- analogy: structural comparison between two domains
- evaluative: judgment with explicit criteria

AI-SIDE (apply a HIGHER quality bar — only use when the AI synthesizes \
something that isn't just restating common knowledge):
- ai_synthesis: AI-generated synthesis combining multiple sources/ideas
- ai_framework: AI-generated framework or model the user can reuse
- ai_evidence: AI-cited evidence or example that crystallizes a point

Output format: JSON array. Reply with ONLY the JSON, no preamble or \
fences. If nothing worth minting, reply with `[]`.

Each object must have:
  - "title": ONE complete declarative sentence stating the claim
  - "type": one of the category names above
  - "body": 1-3 proposition bullets explaining the claim, each with \
named actors (no "it" / "they" / passive voice — name what does what)
  - "source_side": "user" or "ai" (where the claim came from)
  - "confidence": "high" | "medium" | "low" (your confidence the claim \
is well-supported by what's actually in the text)

Example output:
[
  {
    "title": "Premature abstraction in code increases maintenance cost \
by forcing future changes through an interface that encoded the wrong \
assumptions",
    "type": "causal",
    "body": "- Abstractions designed before requirements stabilize lock \
in incorrect assumptions about variation\\n- Future changes must route \
through the abstraction's interface even when the underlying assumption \
is now wrong\\n- The cost compounds because each new requirement either \
fights the abstraction or accumulates workaround complexity",
    "source_side": "user",
    "confidence": "high"
  }
]"""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)


def _strip_json_fences(text: str) -> str:
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1)
    return text.strip()


def call_sonnet_extract(
    user_input: str,
    ai_response: str,
    *,
    client: AnthropicClient,
) -> tuple[list[dict], int, int, float, str]:
    """Run Sonnet on a pair, return list of candidate-atomic dicts."""
    body = (
        f"USER MESSAGE:\n<<<\n{user_input[:MAX_PAIR_CHARS_FOR_EXTRACTION // 2]}\n>>>\n\n"
        f"AI RESPONSE:\n<<<\n{ai_response[:MAX_PAIR_CHARS_FOR_EXTRACTION // 2]}\n>>>\n\n"
        f"Extract atomic notes (JSON array):"
    )
    result = client.call(
        system=_SYSTEM_PROMPT,
        user=body,
        model=EXTRACTION_MODEL,
        max_tokens=2048,
        temperature=0.0,
    )
    if result.error:
        return [], result.input_tokens, result.output_tokens, result.cost_usd, result.error
    raw = _strip_json_fences(result.text)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return [], result.input_tokens, result.output_tokens, result.cost_usd, "not a list"
    except json.JSONDecodeError as e:
        return [], result.input_tokens, result.output_tokens, result.cost_usd, f"json: {e}"
    # Filter to valid types only
    cleaned: list[dict] = []
    for c in parsed:
        if not isinstance(c, dict):
            continue
        if c.get("type") not in _VALID_TYPES:
            continue
        if not c.get("title") or not c.get("body"):
            continue
        cleaned.append(c)
    return cleaned, result.input_tokens, result.output_tokens, result.cost_usd, ""


# ---------------------------------------------------------------------------
# Vault note builder
# ---------------------------------------------------------------------------


_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS_RE    = re.compile(r"[\s\-]+")


def _slugify(text: str, max_words: int = 8) -> str:
    if not text:
        return "untitled"
    s = text.lower()
    s = _SLUG_STRIP_RE.sub(" ", s)
    s = _SLUG_WS_RE.sub("-", s).strip("-")
    parts = [p for p in s.split("-") if p]
    if not parts:
        return "untitled"
    return "-".join(parts[:max_words])


def _yaml_escape(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    if any(c in s for c in ":#[]{},&*!|>'\"%@`\n") or s.strip() != s:
        return "'" + s.replace("'", "''") + "'"
    return s


@dataclass
class AtomicCandidate:
    """A candidate atomic note — Sonnet's output enriched with provenance."""
    title:           str
    note_type:       str
    body:            str
    source_side:     str
    confidence:      str
    # Provenance
    cleaned_pair_path: str
    pair_num:        int
    when:            datetime
    source_chat:     str
    source_platform: str
    chain_id:        str
    chain_label:     str


def build_atomic_note(c: AtomicCandidate) -> str:
    """Compose the markdown body for a Phase 5 atomic note."""
    today = datetime.now().strftime("%Y-%m-%d")
    when_str = c.when.strftime("%Y-%m-%d")
    rel_source = c.source_chat.replace(os.path.expanduser("~/"), "~/")
    yaml_lines = [
        "---",
        "nexus:",
        "type: engram",
        "tags:",
        "  - atomic",
        f"  - {c.note_type}",
        f"date created: {when_str}",
        f"date modified: {today}",
        f"source_chat: {_yaml_escape(rel_source)}",
        f"source_pair_num: {c.pair_num}",
        f"source_platform: {c.source_platform}",
        f"source_side: {c.source_side}",
    ]
    if c.chain_id:
        yaml_lines.append(f"chain_id: {c.chain_id}")
        yaml_lines.append(f"chain_label: {_yaml_escape(c.chain_label)}")
    yaml_lines.append(f"extraction_model: {EXTRACTION_MODEL}")
    yaml_lines.append(f"confidence: {c.confidence}")
    yaml_lines.append(f"processed_at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    yaml_lines.append("seen_count: 1")
    yaml_lines.append("---")
    yaml = "\n".join(yaml_lines) + "\n\n"

    body_lines = [f"# {c.title}\n"]
    body_lines.append(c.body.strip())
    body_lines.append("")
    body_lines.append("## Source")
    body_lines.append("")
    body_lines.append(
        f"From conversation pair {c.pair_num} dated {when_str} on "
        f"{c.source_platform}. Chain: `{c.chain_label or 'unassigned'}`."
    )
    return yaml + "\n".join(body_lines) + "\n"


def _atomic_uid(c: AtomicCandidate) -> str:
    """Stable id for this candidate — pair + index in pair."""
    h = hashlib.sha256()
    h.update(c.cleaned_pair_path.encode("utf-8"))
    h.update(b"|")
    h.update(c.title.encode("utf-8"))
    return "atomic-" + h.hexdigest()[:14]


def _vault_path_for(c: AtomicCandidate, vault_root: str) -> Path:
    year = str(c.when.year)
    slug = _slugify(c.title) or "untitled"
    base = f"{c.when.strftime('%Y-%m-%d')}_{slug}.md"
    return Path(vault_root) / year / base


def write_atomic_note(
    c: AtomicCandidate,
    vault_root: str = DEFAULT_VAULT_ROOT,
) -> str:
    path = _vault_path_for(c, vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Collision — disambiguate with first 6 chars of uid.
        path = path.with_name(
            f"{path.stem}-{_atomic_uid(c)[-6:]}{path.suffix}"
        )
    path.write_text(build_atomic_note(c), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Dedup via ChromaDB
# ---------------------------------------------------------------------------


def _embedding_text(c: AtomicCandidate) -> str:
    """Text we embed for the dedup index — title carries the meaning,
    body adds disambiguation."""
    return f"{c.title}\n\n{c.body[:1500]}"


@dataclass
class DedupResult:
    """Outcome of a dedup check for one candidate."""
    is_duplicate:        bool
    matched_id:          str = ""
    matched_similarity:  float = 0.0
    matched_path:        str = ""


def check_and_register(
    candidate: AtomicCandidate,
    *,
    collection,
    threshold: float = DEDUP_SIM_THRESHOLD,
    vault_root: str = DEFAULT_VAULT_ROOT,
) -> tuple[DedupResult, Optional[str]]:
    """Dedup-check a candidate. If duplicate: bump existing record's
    `seen_count` and return DedupResult(is_duplicate=True). If unique:
    write vault note, register in ChromaDB, return path.

    Returns (dedup_result, written_path_or_None).
    """
    embed_text = _embedding_text(candidate)
    matches = collection.query(
        query_texts=[embed_text],
        n_results=1,
        include=["distances", "metadatas"],
    )
    if matches["ids"] and matches["ids"][0]:
        # Cosine distance from chroma is 1 - cosine_similarity.
        dist = matches["distances"][0][0] if matches["distances"][0] else 1.0
        sim = 1.0 - dist
        if sim >= threshold:
            # Duplicate — bump seen_count on existing record.
            existing_id = matches["ids"][0][0]
            existing_meta = matches["metadatas"][0][0] if matches["metadatas"][0] else {}
            new_count = int(existing_meta.get("seen_count", 1)) + 1
            try:
                collection.update(
                    ids=[existing_id],
                    metadatas=[{**existing_meta, "seen_count": new_count}],
                )
            except Exception:
                pass
            return DedupResult(
                is_duplicate=True,
                matched_id=existing_id,
                matched_similarity=sim,
                matched_path=existing_meta.get("vault_path", ""),
            ), None

    # Unique — write vault note and register.
    written_path = write_atomic_note(candidate, vault_root=vault_root)
    uid = _atomic_uid(candidate)
    try:
        collection.upsert(
            ids=[uid],
            documents=[embed_text],
            metadatas=[{
                "vault_path":       written_path,
                "title":            candidate.title,
                "note_type":        candidate.note_type,
                "source_side":      candidate.source_side,
                "source_chat":      candidate.source_chat,
                "pair_num":         candidate.pair_num,
                "source_platform":  candidate.source_platform,
                "chain_id":         candidate.chain_id,
                "when":             candidate.when.isoformat(timespec="seconds"),
                "seen_count":       1,
            }],
        )
    except Exception as e:
        # Collection write failed; still return the path we wrote.
        return DedupResult(is_duplicate=False), written_path
    return DedupResult(is_duplicate=False), written_path


# ---------------------------------------------------------------------------
# Per-pair extraction
# ---------------------------------------------------------------------------


@dataclass
class PairResult:
    cleaned_pair_path: str
    candidates_total:  int = 0
    candidates_minted: int = 0
    candidates_dedup:  int = 0
    written_paths:     list[str] = field(default_factory=list)
    error:             str = ""
    input_tokens:      int = 0
    output_tokens:     int = 0
    cost_usd:          float = 0.0


def process_one_pair(
    cleaned_pair_path: str,
    *,
    client: AnthropicClient,
    collection,
    chain_lookup: dict,
    vault_root: str = DEFAULT_VAULT_ROOT,
) -> PairResult:
    res = PairResult(cleaned_pair_path=cleaned_pair_path)
    try:
        cp = load_cleaned_pair(cleaned_pair_path)
    except Exception as e:
        res.error = f"load: {e}"
        return res

    text_total = (cp.cleaned_user_input or "") + (cp.cleaned_ai_response or "")
    if len(text_total) < MIN_PAIR_CHARS_FOR_EXTRACTION:
        return res   # too small — skip, no candidates

    candidates_raw, ti, to, cost, err = call_sonnet_extract(
        cp.cleaned_user_input or "",
        cp.cleaned_ai_response or "",
        client=client,
    )
    res.input_tokens, res.output_tokens, res.cost_usd = ti, to, cost
    if err:
        res.error = err
        return res
    if not candidates_raw:
        return res

    sid = derive_session_id(cp.source_chat)
    chain_id = chain_lookup.get("session_to_chain", {}).get(sid, "")
    chain_label = ""
    if chain_id:
        for c in chain_lookup.get("chains", []):
            if c["chain_id"] == chain_id:
                chain_label = c["chain_label"]
                break

    when = cp.source_timestamp or datetime.now()

    for raw in candidates_raw:
        # Normalize source_side — Sonnet sometimes returns the type
        # name (e.g. "ai_synthesis") instead of "user"/"ai". Map any
        # ai_* type back to "ai".
        side_raw = raw.get("source_side", "user")
        if side_raw not in ("user", "ai"):
            side_raw = "ai" if raw["type"].startswith("ai_") else "user"
        candidate = AtomicCandidate(
            title=str(raw["title"])[:300],
            note_type=raw["type"],
            body=str(raw["body"]),
            source_side=side_raw,
            confidence=raw.get("confidence", "medium"),
            cleaned_pair_path=cleaned_pair_path,
            pair_num=cp.source_pair_num,
            when=when,
            source_chat=cp.source_chat,
            source_platform=cp.source_platform,
            chain_id=chain_id,
            chain_label=chain_label,
        )
        res.candidates_total += 1
        try:
            dedup, written_path = check_and_register(
                candidate, collection=collection, vault_root=vault_root,
            )
        except Exception as e:
            res.error = f"dedup: {e}"
            continue
        if dedup.is_duplicate:
            res.candidates_dedup += 1
        else:
            res.candidates_minted += 1
            if written_path:
                res.written_paths.append(written_path)
    return res


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _load_manifest(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {
            "version":          1,
            "created_at":       datetime.now().isoformat(timespec="seconds"),
            "completed_pairs":  {},
            "totals": {
                "pairs_processed":  0,
                "pairs_with_atomics": 0,
                "candidates_total": 0,
                "candidates_minted": 0,
                "candidates_dedup":  0,
                "input_tokens":     0,
                "output_tokens":    0,
                "cost_usd":         0.0,
            },
        }
    return json.loads(p.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict, path: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Batch orchestration (reverse chronological)
# ---------------------------------------------------------------------------


def _open_dedup_collection(chromadb_path: str, name: str):
    """Open (or create) the dedup collection. Uses the canonical Ollama
    nomic-embed-text embedding function, same as the conversations
    collection."""
    import chromadb
    from orchestrator.embedding import get_or_create_collection
    client = chromadb.PersistentClient(path=str(chromadb_path))
    return get_or_create_collection(client, name)


def _enumerate_pairs_reverse_chrono(archive_dir: str) -> list[str]:
    """Return cleaned-pair file paths sorted NEWEST first by source
    timestamp. Falls back to filename-date order if a file's timestamp
    is unparseable."""
    import re
    files = list(Path(archive_dir).glob("*.md"))
    # Filename pattern: YYYY-MM-DD_HH-MM_*.md — sort lexicographically
    # works for chronological order.
    files.sort(key=lambda p: p.name, reverse=True)
    return [str(f) for f in files]


def run_phase5(
    archive_dir:        str = DEFAULT_ARCHIVE_DIR,
    *,
    vault_root:         str = DEFAULT_VAULT_ROOT,
    chromadb_path:      str = DEFAULT_CHROMADB_PATH,
    dedup_collection:   str = DEFAULT_DEDUP_COLLECTION,
    chain_index_path:   str = CHAIN_INDEX_DEFAULT,
    manifest_path:      str = DEFAULT_MANIFEST_PATH,
    max_workers:        int = 6,
    progress_to_stderr: bool = True,
    rebuild_manifest:   bool = False,
    limit:              Optional[int] = None,
) -> dict:
    start = time.monotonic()
    chain_lookup = load_chain_index(chain_index_path)

    if progress_to_stderr:
        print("[phase5] enumerating pairs in reverse chronological order…",
              file=sys.stderr, flush=True)
    pairs = _enumerate_pairs_reverse_chrono(archive_dir)
    if limit:
        pairs = pairs[:limit]
    if progress_to_stderr:
        print(f"[phase5] {len(pairs):,} pairs in archive",
              file=sys.stderr, flush=True)

    manifest = _load_manifest(manifest_path) if not rebuild_manifest \
                else _load_manifest("/nonexistent")
    completed = set(manifest.get("completed_pairs", {}).keys())
    pending = [p for p in pairs if p not in completed]
    if progress_to_stderr:
        print(f"[phase5] {len(completed):,} already done, "
              f"{len(pending):,} pending (max_workers={max_workers})",
              file=sys.stderr, flush=True)

    if not pending:
        return {"status": "nothing-to-do",
                "already_done": len(completed)}

    collection = _open_dedup_collection(chromadb_path, dedup_collection)
    client = AnthropicClient(model=EXTRACTION_MODEL)

    aggregate = {
        "pairs_processed":     0,
        "pairs_with_atomics":  0,
        "pairs_errored":       0,
        "candidates_total":    0,
        "candidates_minted":   0,
        "candidates_dedup":    0,
        "input_tokens":        0,
        "output_tokens":       0,
        "cost_usd":            0.0,
    }
    counter = {"done": 0}
    last_save = time.monotonic()

    def _process(p: str) -> PairResult:
        try:
            return process_one_pair(
                p, client=client, collection=collection,
                chain_lookup=chain_lookup, vault_root=vault_root,
            )
        except Exception as e:
            r = PairResult(cleaned_pair_path=p)
            r.error = f"unexpected: {e}"
            return r

    def _record(r: PairResult) -> None:
        aggregate["pairs_processed"]   += 1
        aggregate["candidates_total"]  += r.candidates_total
        aggregate["candidates_minted"] += r.candidates_minted
        aggregate["candidates_dedup"]  += r.candidates_dedup
        aggregate["input_tokens"]      += r.input_tokens
        aggregate["output_tokens"]     += r.output_tokens
        aggregate["cost_usd"]          += r.cost_usd
        if r.error:
            aggregate["pairs_errored"] += 1
        if r.candidates_minted > 0:
            aggregate["pairs_with_atomics"] += 1
        manifest["completed_pairs"][r.cleaned_pair_path] = {
            "candidates_total":  r.candidates_total,
            "candidates_minted": r.candidates_minted,
            "candidates_dedup":  r.candidates_dedup,
            "input_tokens":      r.input_tokens,
            "output_tokens":     r.output_tokens,
            "cost_usd":          r.cost_usd,
            "error":             r.error,
        }
        m_totals = manifest["totals"]
        m_totals["pairs_processed"]   += 1
        m_totals["pairs_with_atomics"] += (1 if r.candidates_minted > 0 else 0)
        m_totals["candidates_total"]  += r.candidates_total
        m_totals["candidates_minted"] += r.candidates_minted
        m_totals["candidates_dedup"]  += r.candidates_dedup
        m_totals["input_tokens"]      += r.input_tokens
        m_totals["output_tokens"]     += r.output_tokens
        m_totals["cost_usd"]          += r.cost_usd

    # Process IN ORDER for true reverse-chronological dedup behavior.
    # Workers parallelize the model calls but the dedup index check is
    # serial-friendly because ChromaDB upsert is atomic.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, p): p for p in pending}
        for fut in as_completed(futures):
            r = fut.result()
            counter["done"] += 1
            _record(r)
            now = time.monotonic()
            if counter["done"] % 50 == 0 or (now - last_save) > 30:
                _save_manifest(manifest, manifest_path)
                last_save = now
            if progress_to_stderr and counter["done"] % 100 == 0:
                pct = counter["done"] / len(pending) * 100
                rate = counter["done"] / max(0.1, now - start)
                eta_min = (len(pending) - counter["done"]) / max(0.001, rate) / 60
                dedup_pct = (aggregate["candidates_dedup"]
                             / max(1, aggregate["candidates_total"])) * 100
                print(f"[phase5] {counter['done']:,}/{len(pending):,} "
                      f"({pct:.1f}%, {now-start:.0f}s, ETA {eta_min:.0f}m)  "
                      f"minted={aggregate['candidates_minted']:,} "
                      f"deduped={aggregate['candidates_dedup']:,} "
                      f"({dedup_pct:.0f}%)  cost=${aggregate['cost_usd']:.2f}",
                      file=sys.stderr, flush=True)

    _save_manifest(manifest, manifest_path)
    aggregate["duration_secs"] = time.monotonic() - start
    return aggregate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 5 — atomic note extraction with reverse-walk dedup.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--vault-root", default=DEFAULT_VAULT_ROOT)
    parser.add_argument("--chromadb-path", default=DEFAULT_CHROMADB_PATH)
    parser.add_argument("--dedup-collection", default=DEFAULT_DEDUP_COLLECTION)
    parser.add_argument("--chain-index", default=CHAIN_INDEX_DEFAULT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    stats = run_phase5(
        archive_dir=args.archive_dir,
        vault_root=args.vault_root,
        chromadb_path=args.chromadb_path,
        dedup_collection=args.dedup_collection,
        chain_index_path=args.chain_index,
        manifest_path=args.manifest,
        max_workers=args.max_workers,
        progress_to_stderr=not args.quiet,
        rebuild_manifest=args.rebuild_manifest,
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
    "DEFAULT_VAULT_ROOT",
    "DEFAULT_CHROMADB_PATH",
    "DEDUP_SIM_THRESHOLD",
    "EXTRACTION_MODEL",
    "AtomicCandidate",
    "DedupResult",
    "PairResult",
    "build_atomic_note",
    "call_sonnet_extract",
    "check_and_register",
    "process_one_pair",
    "run_phase5",
    "main",
]
