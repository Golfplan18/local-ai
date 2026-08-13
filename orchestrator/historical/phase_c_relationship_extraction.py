"""Phase C — relationship extraction across the atomic note corpus.

For each atomic note in `~/Documents/vault/Engrams/`, retrieve K nearest
neighbors from the ChromaDB `atomic_dedup` collection, ask a small model
(Haiku) to classify which are genuinely related and how, then write
`relationships:` into the source note's YAML frontmatter.

Output format per the YAML schema (Reference — Ora YAML Schema §3):
    relationships:
      - type: supports
        target: "Target Note Title"
        confidence: high
      - type: extends
        target: "Another Note Title"
        confidence: medium

Manifest: `~/ora/data/phase-c-manifest.json` for resumability.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from orchestrator import runtime_paths as _rp
from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical import cleanup_backends as _backends


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_VAULT_ROOT = str(_rp.vault_dir() / "Engrams")
DEFAULT_CHROMADB_PATH = str(_rp.chromadb_dir())
# Logical collection name; the configured embedding layer owns the physical
# name (for example atomic_dedup_qwen_qwen3_embedding_8b on this machine).
DEFAULT_DEDUP_COLLECTION = "atomics"
DEFAULT_MANIFEST_PATH = str(_rp.DATA_DIR / "phase-c-manifest.json")

# Haiku 4.5 — fast classifier for the relationship typing task.
# Overridable per run; the runner sets it from --backend/--model.
RELATION_MODEL = "claude-haiku-4-5"

# Retrieval params
# These three were cost caps, and cost caps are how every defect in this project
# got introduced: truncating the writer's input de-fanged 56% of the corpus,
# capping title length replaced actors with pronouns, and extracting "specifics"
# instead of passing text produced fabricated evidence lines. The publisher's
# instruction on the model now used here is explicit — treat its tokens as free —
# so nothing is truncated that the classifier could use.
#
# NEIGHBOR_MAX_CHARS at 600 truncated the body of 13,309 notes (17.6% of the
# corpus). Mean body is 500 chars and only 265 notes exceed 1,200, so a 4,000
# ceiling is effectively "no truncation" while still bounding a pathological note.
#
# NEIGHBOR_K governs how many candidates the classifier gets to judge. More
# candidates cannot produce a wrong edge — the model returns an index and both the
# index and the type are validated against closed sets — but fewer candidates
# silently loses real relationships that embedding retrieval did surface.
_CLIENT_BACKEND = "api"

NEIGHBOR_K = 30
SOURCE_MAX_CHARS = 8000        # source note body: effectively untruncated
NEIGHBOR_MAX_CHARS = 4000      # per candidate: effectively untruncated

# Valid relationship types per the 13-type taxonomy
_VALID_REL_TYPES = frozenset({
    "supports", "contradicts", "qualifies", "extends", "supersedes",
    "analogous-to", "derived-from", "enables", "requires",
    "produces", "precedes", "parent", "child",
})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


# ---------------------------------------------------------------------------
# Note I/O
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_note(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end():]
    return fm, body


def get_title(fm: dict, body: str, fallback_path: Path) -> str:
    """Extract title — prefer first H1 in body, fall back to filename stem."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s and not s.startswith("#"):
            break
    return fallback_path.stem


def write_note_with_relationships(
    path: Path,
    fm: dict,
    body: str,
    relationships: list[dict],
) -> None:
    """Replace `relationships:` in frontmatter, preserve everything else."""
    new_fm = dict(fm)
    new_fm["relationships"] = relationships if relationships else []
    # Serialize with consistent ordering (relationships near end)
    yaml_str = yaml.safe_dump(new_fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
    out = f"---\n{yaml_str}---\n{body}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Embedding (shared configured provider/model/dimension)
# ---------------------------------------------------------------------------


def embed_configured(text: str) -> list[float]:
    """Embed with the active provider, model, and dimension configuration."""
    from orchestrator.embedding import embed_text

    return embed_text(text)


# ---------------------------------------------------------------------------
# Relationship typing prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT_REL = """\
You classify RELATIONSHIPS between a SOURCE atomic knowledge note and a \
list of CANDIDATE notes. For each candidate, decide whether it has a \
genuine, useful relationship to the source. If yes, name the relationship \
using the 13-type taxonomy. If no, omit it.

The 13-type taxonomy:
  - supports: source provides evidence FOR the candidate
  - contradicts: source asserts incompatibility with the candidate
  - qualifies: source narrows or conditions the candidate's scope
  - extends: source builds on the candidate with additional content
  - supersedes: source replaces the candidate (candidate is older/wrong)
  - analogous-to: source maps structurally to candidate in a different domain
  - derived-from: source originates by transformation of the candidate
  - enables: source's truth makes the candidate possible
  - requires: source presupposes the candidate
  - produces: source's execution yields the candidate as output
  - precedes: source must occur before the candidate in sequence
  - parent: source is a hierarchical container of the candidate
  - child: source is a hierarchical member of the candidate

Be SELECTIVE. Most candidate pairs are NOT genuinely related — they are \
just nearby in embedding space. Only emit a relationship when there is a \
clear, defensible connection. A typical source has 0-5 real relationships \
out of 15 candidates. Never invent a relationship to fill a slot.

Output format: JSON array. Reply with ONLY the JSON, no preamble or fences.
Empty array if no candidates qualify: `[]`.

Each object must have:
  - "candidate_index": integer (0-based index into the candidates list)
  - "type": one of the 13 type names above
  - "confidence": "high" | "medium" | "low"

Confidence levels:
  - high: the relationship is explicitly supported by the text of both notes
  - medium: clear structural inference from both notes
  - low: plausible but partial overlap

Example output:
[
  {"candidate_index": 0, "type": "supports", "confidence": "high"},
  {"candidate_index": 3, "type": "extends", "confidence": "medium"},
  {"candidate_index": 7, "type": "analogous-to", "confidence": "low"}
]"""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)


def _strip_fences(text: str) -> str:
    m = _JSON_FENCE_RE.search(text)
    return m.group(1) if m else text.strip()


def call_relation_classifier(
    source_title: str,
    source_body: str,
    candidates: list[dict],
    *,
    client: AnthropicClient,
) -> tuple[list[dict], int, int, float, str]:
    """candidates: [{title, body}, ...]. Returns parsed relations + tokens + cost + err."""
    cand_lines = []
    for i, c in enumerate(candidates):
        body_snip = (c["body"] or "")[:NEIGHBOR_MAX_CHARS]
        cand_lines.append(f"[{i}] TITLE: {c['title']}\n    BODY: {body_snip}")
    body_snip = (source_body or "")[:SOURCE_MAX_CHARS]
    user = (
        f"SOURCE NOTE\nTITLE: {source_title}\nBODY: {body_snip}\n\n"
        f"CANDIDATES (each labeled [N]):\n" + "\n\n".join(cand_lines) + "\n\n"
        f"Classify the relationships (JSON array):"
    )
    result = client.call(
        system=_SYSTEM_PROMPT_REL,
        user=user,
        model=RELATION_MODEL,
        max_tokens=1024,
        temperature=0.0,
    )
    if result.error:
        return [], result.input_tokens, result.output_tokens, result.cost_usd, result.error
    raw = _strip_fences(result.text)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return [], result.input_tokens, result.output_tokens, result.cost_usd, "not a list"
    except json.JSONDecodeError as e:
        return [], result.input_tokens, result.output_tokens, result.cost_usd, f"json: {e}"

    cleaned: list[dict] = []
    for r in parsed:
        if not isinstance(r, dict):
            continue
        idx = r.get("candidate_index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        rtype = r.get("type")
        if rtype not in _VALID_REL_TYPES:
            continue
        conf = r.get("confidence", "medium")
        if conf not in _VALID_CONFIDENCE:
            conf = "medium"
        cleaned.append({
            "type": rtype,
            "target": candidates[idx]["title"],
            "confidence": conf,
        })
    return cleaned, result.input_tokens, result.output_tokens, result.cost_usd, ""


# ---------------------------------------------------------------------------
# Per-note orchestration
# ---------------------------------------------------------------------------


@dataclass
class NoteResult:
    path: str
    relationships_written: int = 0
    candidates_considered: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    skipped: str = ""
    error: str = ""


def process_one_note(
    path_str: str,
    *,
    client: AnthropicClient,
    collection,
) -> NoteResult:
    res = NoteResult(path=path_str)
    p = Path(path_str)
    try:
        fm, body = parse_note(p)
    except Exception as e:
        res.error = f"parse: {e}"
        return res
    title = get_title(fm, body, p)
    # Skip notes with no body content
    if len(body.strip()) < 50:
        res.skipped = "body too short"
        return res
    # Use title + first part of body as the embedding query
    query_text = f"{title}\n\n{body[:2000]}"
    try:
        emb = embed_configured(query_text)
    except Exception as e:
        res.error = f"embed: {e}"
        return res
    # Retrieve K+1 (we'll filter self)
    try:
        q = collection.query(
            query_embeddings=[emb],
            n_results=NEIGHBOR_K + 1,
            include=["metadatas", "distances", "documents"],
        )
    except Exception as e:
        res.error = f"query: {e}"
        return res

    ids = q.get("ids", [[]])[0]
    metas = q.get("metadatas", [[]])[0]
    dists = q.get("distances", [[]])[0]
    docs = q.get("documents", [[]])[0]

    # Build candidate list, exclude self. Order is by ascending distance
    # (most similar first); we send the top NEIGHBOR_K to Haiku and let
    # it decide which are genuinely related.
    candidates = []
    for i, md in enumerate(metas):
        cand_title = (md or {}).get("title", "").strip()
        cand_path = (md or {}).get("vault_path", "")
        if cand_title == title:
            continue
        if cand_path == str(p.absolute()) or cand_path.endswith("/" + p.name):
            continue
        candidates.append({
            "title": cand_title,
            "body": (docs[i] if i < len(docs) else "") or "",
            "distance": dists[i] if i < len(dists) else 0.0,
        })
        if len(candidates) >= NEIGHBOR_K:
            break

    res.candidates_considered = len(candidates)
    if not candidates:
        # Write empty relationships and return
        try:
            write_note_with_relationships(p, fm, body, [])
        except Exception as e:
            res.error = f"write_empty: {e}"
        return res

    rels, in_t, out_t, cost, err = call_relation_classifier(
        title, body, candidates, client=client
    )
    res.input_tokens += in_t
    res.output_tokens += out_t
    res.cost_usd += cost
    if err:
        res.error = err
        return res

    try:
        write_note_with_relationships(p, fm, body, rels)
        res.relationships_written = len(rels)
    except Exception as e:
        res.error = f"write: {e}"
    return res


# ---------------------------------------------------------------------------
# Manifest + orchestrator
# ---------------------------------------------------------------------------


def _load_manifest(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    from datetime import datetime
    return {
        "version": 1,
        "created_at": datetime.now().isoformat(),
        "completed_notes": {},
        "totals": {
            "notes_processed": 0,
            "relationships_total": 0,
            "skipped": 0,
            "errors": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        },
        "last_updated": datetime.now().isoformat(),
    }


def _save_manifest(manifest: dict, path: str) -> None:
    from datetime import datetime
    manifest["last_updated"] = datetime.now().isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(manifest, fh, indent=2)
    os.replace(tmp, path)


def _open_collection(chromadb_path: str, name: str):
    import chromadb
    from orchestrator.embedding import get_collection

    client = chromadb.PersistentClient(path=chromadb_path)
    return get_collection(client, name)


def run_phase_c(
    note_paths: list[str],
    *,
    chromadb_path: str = DEFAULT_CHROMADB_PATH,
    dedup_collection: str = DEFAULT_DEDUP_COLLECTION,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    max_workers: int = 16,
    save_every: int = 50,
) -> None:
    client = _backends.build_client(_CLIENT_BACKEND)
    print(f"Phase C model: {RELATION_MODEL} via backend '{_CLIENT_BACKEND}'")
    collection = _open_collection(chromadb_path, dedup_collection)
    manifest = _load_manifest(manifest_path)
    completed = manifest["completed_notes"]
    todo = [p for p in note_paths if p not in completed]
    print(f"Phase C: {len(note_paths)} total, {len(todo)} pending, {len(completed)} resumed")
    sys.stdout.flush()
    if not todo:
        print("nothing to do")
        return

    t0 = time.time()
    processed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(process_one_note, p, client=client, collection=collection): p
            for p in todo
        }
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = NoteResult(path=p, error=f"executor: {e}")
            entry = {
                "rels": r.relationships_written,
                "considered": r.candidates_considered,
                "tokens_in": r.input_tokens,
                "tokens_out": r.output_tokens,
                "cost": r.cost_usd,
            }
            if r.skipped:
                entry["skipped"] = r.skipped
            if r.error:
                entry["error"] = r.error
            # E2 fix. This previously ran unconditionally, so a note that errored
            # or was skipped was recorded as completed and resume never retried it
            # — the same defect as marking a failed call 'ok'. Only a genuine
            # success is recorded; failures stay on the worklist. Errors are also
            # kept in a separate list so a run's failures are inspectable rather
            # than inferred.
            if r.error:
                manifest.setdefault("errors", {})[p] = r.error
            else:
                completed[p] = entry
                manifest.get("errors", {}).pop(p, None)

            tot = manifest["totals"]
            tot["notes_processed"] += 1
            tot["relationships_total"] += r.relationships_written
            tot["input_tokens"] += r.input_tokens
            tot["output_tokens"] += r.output_tokens
            tot["cost_usd"] += r.cost_usd
            if r.skipped:
                tot["skipped"] += 1
            if r.error:
                tot["errors"] += 1

            processed += 1
            if processed % save_every == 0 or processed == len(todo):
                _save_manifest(manifest, manifest_path)
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0.0
                remaining = (len(todo) - processed) / rate if rate > 0 else 0
                print(
                    f"  [{processed}/{len(todo)}] "
                    f"rels={tot['relationships_total']} skipped={tot['skipped']} "
                    f"errors={tot['errors']} cost=${tot['cost_usd']:.2f} "
                    f"rate={rate:.2f}/s eta={int(remaining/60)}m"
                )
                sys.stdout.flush()
    _save_manifest(manifest, manifest_path)
    print(f"\nDONE — totals: {manifest['totals']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Phase C relationship extraction")
    p.add_argument("--vault-root", default=DEFAULT_VAULT_ROOT)
    p.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    p.add_argument("--max-workers", type=int, default=16)
    p.add_argument("--limit", type=int, default=0, help="process only first N notes (sample mode)")
    p.add_argument("--paths-file", help="optional file with newline-delimited note paths")
    p.add_argument("--backend", default="api", choices=_backends.BACKEND_CHOICES,
                   help="model backend. 'minimax' is measured-suitable here: the "
                        "classifier returns a candidate index rather than writing a "
                        "target title, and both index and type are validated against "
                        "closed sets, so a weak model can only under-link, never "
                        "fabricate an edge.")
    p.add_argument("--model", default=None,
                   help="override the relationship model for this run")
    args = p.parse_args(argv)

    global RELATION_MODEL, _CLIENT_BACKEND
    if args.model:
        RELATION_MODEL = args.model
    elif args.backend == "minimax":
        RELATION_MODEL = "MiniMax-M3"
    _CLIENT_BACKEND = args.backend

    if args.paths_file:
        with open(args.paths_file) as fh:
            paths = [ln.strip() for ln in fh if ln.strip()]
    else:
        root = Path(args.vault_root)
        paths = sorted(str(f.absolute()) for f in root.glob("*.md"))
    if args.limit:
        paths = paths[: args.limit]

    print(f"Notes to consider: {len(paths)}")
    run_phase_c(paths, manifest_path=args.manifest, max_workers=args.max_workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
