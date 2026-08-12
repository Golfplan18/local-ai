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
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator import runtime_paths as _rp
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

DEFAULT_ARCHIVE_DIR    = str(_rp.historical_archive_dir())
DEFAULT_VAULT_ROOT     = str(_rp.vault_dir() / "Engrams" / "Historical Atomics")
DEFAULT_CHROMADB_PATH  = str(_rp.chromadb_dir())
# Logical collection name. embedding.resolve_collection() maps this to the
# machine-specific physical collection configured in config/chromadb.json.
DEFAULT_DEDUP_COLLECTION = "atomics"
DEFAULT_MANIFEST_PATH  = str(_rp.DATA_DIR / "phase5-manifest.json")
DEFAULT_REPORT_PATH    = str(_rp.DATA_DIR / "phase5-report.json")

# Extraction model — Mimo-V2.5-Pro via OpenRouter.
# The hint is an OpenRouter slug (contains "/") so the OpenRouter client
# passes it to the API unchanged via resolve_model's slug pass-through.
EXTRACTION_MODEL = "xiaomi/mimo-v2.5-pro"

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
You extract PERMANENT NOTES from a single conversation turn pair (user \
message + AI response).

A permanent note is NOT a record of what was said. It states a claim in \
general form, detached from the conversation it came from, at a level of \
abstraction that transfers to other domains. The specific case from the \
conversation is retained beneath the claim as EVIDENCE, never as the \
claim itself.

=== TRANSFER TEST — apply to every candidate before you emit it ===
Could this claim be usefully applied by someone working in a domain \
unrelated to this conversation? If not, either restate it one level more \
general so that it can be, or do not mint it at all. A claim that only \
makes sense inside this conversation's own subject matter is a record of \
what was said, not a knowledge building block. Do not mint it.

Be SELECTIVE. A typical pair yields 0-3 notes; a substantive deep dive \
might yield up to 8. Small talk, status updates, and generic Q&A yield [].

=== DO NOT MINT BARE FACTS ===
A verifiable empirical claim is evidence, not a building block. Attach it \
as the "Instance:" bullet of the principle it demonstrates. Mint a \
standalone `fact` note ONLY when it is BOTH (a) not general knowledge a \
competent model already carries, AND (b) personal, local, or proprietary \
to this user — their own observation, their own measurement, their own \
project. Dated news items and textbook facts are never minted.

Categories:

USER-SIDE:
- principle: generalizable rule about how something works
- definition: precise definition of a concept
- causal: assertion that one thing causes / prevents / enables another
- analogy: structural comparison between two domains
- evaluative: judgment with explicit criteria
- fact: personal/local/proprietary only, per the rule above

AI-SIDE (apply a HIGHER quality bar — only when the AI synthesizes \
something that isn't just restating common knowledge):
- ai_synthesis: AI-generated synthesis combining multiple sources/ideas
- ai_framework: AI-generated framework or model the user can reuse
- ai_evidence: AI-cited evidence or example that crystallizes a point

=== TITLE ===
ONE declarative sentence stating the claim. NEVER put in a title:
  - proper nouns (people, companies, statutes, products, places) unless \
the note exists to define that entity
  - dates, years, "currently", "recently"
  - a because.../when.../by ...ing clause explaining the mechanism — the \
title asserts THAT, the body explains HOW
  - a domain qualifier that is not load-bearing ("in coal towns", "in \
early dating", "in narrative")
  - hedges that dissolve the claim (can, may, often, typically, sometimes)
  - inventory counts ("nine major areas", "three types")
  - the user's private vocabulary or fiction character names
  - absolutes the body does not establish: no "cannot", "always", \
"never", "proves"
WHERE A STANDARD NAME FOR THE CONCEPT EXISTS — salience bias, moral \
hazard, regulatory capture, debt peonage, operant extinction, \
routinization of charisma, Goodhart's law — USE IT VERBATIM in the title, \
or failing that verbatim in a body bullet. This corpus is searched by \
keyword AND by meaning; a note matching neither is dead. Naming the \
concept only in your reasoning is a FAILURE.
Impose no length limit. A correct general claim is short as a \
consequence, never as a target.

=== BODY ===
2-4 bullets.
  - The FIRST bullets state the mechanism in domain-neutral terms. Name \
the ROLES that act — the incumbent, the regulator, the borrower, the \
performer — not the individuals who happened to act in this conversation. \
Active voice throughout: every bullet says what does what. No "it" / \
"they" / passive voice.
  - The LAST bullet begins "Instance:" and carries the specific case from \
this conversation — names, numbers, dates, domain nouns intact. This is \
the evidence, and it is what keeps the note findable by keyword.
  - The Instance line may contain ONLY specifics that appear in this \
conversation. Never introduce an example, statistic, or illustration that \
is not in the source. If the pair carried no concrete case, write \
"Instance: none recorded in source." An invented instance is \
indistinguishable from a real record and corrupts the evidence layer.

=== FAILURE MODE TO AVOID ===
Over-generalization into platitude. "Systems tend to favour those with \
power" is useless. The general claim must remain FALSIFIABLE and SPECIFIC \
about the mechanism — raised one level, not dissolved. If raising the \
level would produce a platitude, do not mint the note.

Output format: JSON array. Reply with ONLY the JSON, no preamble or \
fences. If nothing is worth minting, reply with `[]`.

Each object must have:
  - "title": the general claim, per the TITLE rules
  - "type": one of the category names above
  - "standard_concept": the canonical name for this concept if one \
exists, else "" — and if non-empty it MUST also appear in title or body
  - "body": the bullets, per the BODY rules
  - "source_side": "user" or "ai" (where the claim came from)
  - "confidence": "high" | "medium" | "low"

Example output:
[
  {
    "title": "Premature abstraction locks in assumptions about variation \
that later requirements must route around",
    "type": "causal",
    "standard_concept": "premature abstraction",
    "body": "- The designer commits to an interface before the pattern of \
variation is known, freezing a guess about what will change\\n- Every \
later requirement either fights that interface or accumulates a \
workaround beside it, so cost compounds instead of staying flat\\n- \
Instance: abstractions designed before requirements stabilize force \
future changes through an interface whose assumption is now wrong",
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
    # Canonical name for the concept, when one exists. Also required to
    # appear verbatim in title or body — this field is the retrieval
    # handle, not a substitute for putting the term in the note.
    standard_concept: str = ""


def build_atomic_note(c: AtomicCandidate) -> str:
    """Compose the markdown body for a Phase 5 atomic note."""
    today = datetime.now().strftime("%Y-%m-%d")
    when_str = c.when.strftime("%Y-%m-%d")
    rel_source = _rp.home_relative_display(c.source_chat)
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
    if c.standard_concept:
        yaml_lines.append(f"standard_concept: {_yaml_escape(c.standard_concept)}")
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
            standard_concept=str(raw.get("standard_concept", "") or "")[:120],
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


_TOTAL_DEFAULTS = {
    "pairs_processed": 0,
    "pairs_with_atomics": 0,
    "candidates_total": 0,
    "candidates_minted": 0,
    "candidates_dedup": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0,
}


def _normalize_manifest(manifest: dict) -> dict:
    """Bring legacy/reconstructed manifests up to the writable schema.

    The emergency 2026-07-10 reconstruction preserved ``completed_pairs``
    but omitted ``totals``.  Phase 5 used to index that mapping directly,
    crashing on the first completed future and losing the whole cycle's
    checkpoint.  Normalize every counter here and again at record time so a
    partial manifest can never recreate that failure.
    """
    if not isinstance(manifest, dict):
        raise ValueError("phase5 manifest root must be an object")

    completed = manifest.setdefault("completed_pairs", {})
    if not isinstance(completed, dict):
        raise ValueError("phase5 manifest completed_pairs must be an object")

    totals = manifest.get("totals")
    if not isinstance(totals, dict):
        totals = {}
        manifest["totals"] = totals
    for key, default in _TOTAL_DEFAULTS.items():
        # A reconstructed manifest knows how many pairs were completed even
        # though its candidate/token history was lost.
        if key == "pairs_processed":
            default = len(completed)
        totals.setdefault(key, default)
    return manifest


def _successful_completed_paths(manifest: dict) -> set[str]:
    """Return paths whose latest Phase 5 attempt completed without error.

    Older code treated an errored result as permanently complete because the
    path was present in ``completed_pairs``.  Keeping errored paths out of the
    resume set makes the next invocation retry them and lets a later success
    overwrite the failed entry.
    """
    completed = manifest.get("completed_pairs", {})
    return {
        path for path, entry in completed.items()
        if not (isinstance(entry, dict) and entry.get("error"))
    }


def _empty_manifest() -> dict:
    return _normalize_manifest({
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "completed_pairs": {},
        "totals": dict(_TOTAL_DEFAULTS),
    })


def _load_manifest(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return _empty_manifest()
    return _normalize_manifest(json.loads(p.read_text(encoding="utf-8")))


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
    """Open the dedup collection with the active configured embedder.

    The same logical atomic collection and provider/model/dimension profile
    are shared by the historical extraction pipelines.
    """
    import chromadb
    from orchestrator.embedding import get_collection
    client = chromadb.PersistentClient(path=str(chromadb_path))
    # Phase 5 resumes against the prebuilt atomic dedup corpus. Opening that
    # existing collection must not take the catalog-write path: on a live
    # persistent store, get_or_create_collection can wait indefinitely behind
    # another Chroma client even though the collection already exists.
    # Missing collections are a recovery/configuration error and should fail
    # loudly rather than silently creating an empty dedup corpus.
    return get_collection(client, name)


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
    limit_pending:      Optional[int] = None,
    backend:            str = "api",
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
                else _empty_manifest()
    completed = _successful_completed_paths(manifest)
    retry_errors = sum(
        1 for entry in manifest.get("completed_pairs", {}).values()
        if isinstance(entry, dict) and entry.get("error")
    )
    pending = [p for p in pairs if p not in completed]
    if limit_pending:
        # Cap the PENDING queue (not the enumerated archive) so a pilot can
        # process exactly one outstanding pair without touching the manifest
        # of already-completed work. ``limit`` caps the archive enumeration
        # and is kept for backward compatibility.
        pending = pending[:limit_pending]
    if progress_to_stderr:
        print(f"[phase5] {len(completed):,} already done, "
              f"{len(pending):,} pending ({retry_errors:,} prior errors "
              f"eligible for retry; max_workers={max_workers})",
              file=sys.stderr, flush=True)

    if not pending:
        return {"status": "nothing-to-do",
                "already_done": len(completed)}

    collection = _open_dedup_collection(chromadb_path, dedup_collection)
    # Every extraction call passes model=EXTRACTION_MODEL explicitly, so
    # non-api backends translate it themselves (tier alias / slot).
    if backend and backend != "api":
        from orchestrator.historical.cleanup_backends import build_client
        client = build_client(backend)
    else:
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
        _normalize_manifest(manifest)
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
    parser.add_argument("--limit", type=int,
                        help="Cap the enumerated archive (newest-first)")
    parser.add_argument("--limit-pending", type=int,
                        help="Cap the PENDING queue (post-resume) — use 1 "
                             "for a single-pair pilot through the selected "
                             "backend without touching completed work")
    parser.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    from orchestrator.historical.cleanup_backends import BACKEND_CHOICES
    parser.add_argument("--backend", choices=list(BACKEND_CHOICES),
                        default="api",
                        help="Model-call path: 'api' (metered Anthropic — "
                             "forbidden for the OpenRouter recovery), "
                             "'claude-cli' (Claude subscription CLI), "
                             "'ora-slots' (Ora slot routing — provider set "
                             "by routing-config), 'openrouter' (explicit "
                             "OpenRouter-only route via openrouter.ai)")
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
        limit_pending=args.limit_pending,
        backend=args.backend,
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
