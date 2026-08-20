#!/usr/bin/env python3
"""Associate archived conversation segments with registered projects.

One script, four subcommands, run in order:

    profiles     matrices + project records -> one retrieval profile per project
    retrieve     multi-route vector retrieval -> segment-level candidates
    judge-input  candidate batches + aimed excerpts -> agent input files
    collect      validate agent verdict files -> the accepted set
    bind         accepted segments -> conversation project membership

The judgment pass between ``judge-input`` and ``collect`` runs as Claude Code
subagents (the user's subscription), not through Ora's model dispatch. Its
prompt lives in ``scripts/judge-conversation-projects.workflow.js``, which is
the operative artifact for that stage; this script writes the input files the
prompt names and reads the verdict files back.

The judgment criteria that prompt encodes turn on "would someone researching
this project want to read this segment", not "is this project the segment's
headline topic". The narrower reading rejects a conversation in which the
user spends several paragraphs describing a project, merely because the
segment around it is filed under something else -- which is how one project
first came back with zero accepted segments out of 651.

Every stage persists to ``data/conversation-projects/`` so a run interrupted
by a session limit resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import collections
import re
import tempfile
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ORA = Path(os.environ.get("ORA_HOME", Path(__file__).resolve().parent.parent))
VAULT = Path(os.environ.get("ORA_VAULT", Path.home() / "Documents" / "vault"))
MATRIX_DIR = VAULT / "Matrix"
PROJECT_DIR = ORA / "data" / "projects"
SEGMENT_DIR = ORA / "data" / "conversation-segments"
OUT_DIR = ORA / "data" / "conversation-projects"

sys.path.insert(0, str(ORA))


# ---------------------------------------------------------------------------
# Shared loaders
# ---------------------------------------------------------------------------


def load_segments() -> dict[str, list[dict]]:
    """Merge every tranche file; later tranches win (tranche-10 holds repairs)."""
    segments: dict[str, list[dict]] = {}
    for path in sorted(SEGMENT_DIR.glob("tranche-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for conv in data["conversations"]:
            segments[conv["conversation_id"]] = conv["segments"]
    return segments


def load_project_records() -> dict[str, dict]:
    records = {}
    for path in sorted(PROJECT_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        nexus = record.get("nexus") or path.stem
        records[nexus] = record
    return records


def _frontmatter_nexus(text: str) -> list[str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return []
    block = match.group(1)
    if "nexus:" not in block:
        return []
    after = block.split("nexus:", 1)[1]
    head, _, rest = after.partition("\n")
    if head.strip():
        return [head.strip()]
    out = []
    for line in rest.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            out.append(stripped[2:].strip())
        elif stripped and not stripped.startswith("-"):
            break
    return out


def load_matrices() -> dict[str, tuple[str, str]]:
    """nexus -> (matrix filename, matrix body)."""
    out = {}
    for path in sorted(MATRIX_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for nexus in _frontmatter_nexus(text):
            out[nexus] = (path.name, text)
    return out


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------

_SUPERSEDED = re.compile(r"^##\s+Historical Milestone Evidence", re.M)


def _section(text: str, heading: str) -> str:
    """Body of one ``## heading`` section, stopping at the next H2."""
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _labelled(section: str, label: str) -> list[str]:
    return [
        m.strip()
        for m in re.findall(rf"\*\*{re.escape(label)}:?\*\*\s*(.+?)$", section, re.M)
    ]


def _bullets(section: str) -> list[str]:
    out = []
    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ", "1. ")):
            continue
        stripped = re.sub(r"^(?:[-*]|\d+\.)\s+", "", stripped)
        stripped = re.sub(r"^\[[ x]\]\s*", "", stripped)
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
        if stripped:
            out.append(stripped)
    return out


def _strip_superseded(text: str) -> str:
    match = _SUPERSEDED.search(text)
    return text[: match.start()] if match else text


# One registered project has no vault matrix. Its retrieval profile is derived
# from its own repository (README, ora-project.json, and the site's page set)
# so it can be retrieved for at all; ora_foundation keeps the foundation's own
# matrix, and the two stay distinct as the project records already have them.
_MATRIXLESS_PROFILES = {
    "ora-ai-org": {
        "core_essence": (
            "To publish and maintain ora-ai.org, the public website of the Ora "
            "Knowledge Foundation, presenting its governance, statement of intent, "
            "philosophy, and framework library as public-domain work."
        ),
        "resolution": (
            "The ora-ai.org static site is built and deployed from the "
            "Golfplan18/ora-ai-org Astro repository, sharing chassis, palette and "
            "typography with Main Street Independent and ora-ai.app, with all work "
            "released under CC0."
        ),
        "objectives": [
            "To build and deploy the ora-ai.org static site with Astro and a "
            "server-pull deployment to the Hetzner origin behind Cloudflare.",
            "To write and publish the foundation's public pages: mission, "
            "governance, statement of intent, philosophy, launch essay, donate, "
            "sources, and public-domain defense.",
            "To present the framework library and knowledge library as browsable "
            "public-domain programs on the website.",
        ],
        "emotional_drivers": [],
        "milestones": [],
        "excluded": [],
        "directions": [],
        "practices": [],
        "distinctive_entities_seed": [
            "ora-ai.org", "Ora Knowledge Foundation", "Astro", "CC0",
            "public domain", "Cloudflare", "statement of intent", "governance",
            "launch essay", "neurodivergent service", "software displacement",
        ],
    },
}


def build_profiles() -> dict[str, dict]:
    records = load_project_records()
    matrices = load_matrices()
    profiles: dict[str, dict] = {}

    for nexus, record in records.items():
        name = record.get("display_name") or record.get("name") or nexus
        entry = {
            "nexus": nexus,
            "name": name,
            "aliases": sorted(
                {
                    v
                    for v in (record.get("name"), record.get("display_name"), record.get("folder_name"))
                    if v
                }
            ),
            "matrix": None,
            "resolution": "",
            "core_essence": "",
            "emotional_drivers": [],
            "objectives": [],
            "milestones": [],
            "excluded": [],
            "directions": [],
            "practices": [],
            "routes": [],
        }
        fallback = _MATRIXLESS_PROFILES.get(nexus)
        found = matrices.get(nexus)
        if not found and fallback:
            entry.update({k: v for k, v in fallback.items() if k != "distinctive_entities_seed"})
            entry["_entity_seed"] = fallback["distinctive_entities_seed"]
        if found:
            filename, raw = found
            text = _strip_superseded(raw)
            entry["matrix"] = filename
            mission = _section(text, "Mission")
            entry["resolution"] = (_labelled(mission, "Resolution Statement") or [""])[0]
            entry["core_essence"] = (_labelled(mission, "Core Essence") or [""])[0]
            drivers = mission.split("Emotional Drivers", 1)
            entry["emotional_drivers"] = _bullets(drivers[1]) if len(drivers) > 1 else []
            entry["objectives"] = _bullets(_section(text, "Objectives"))
            milestones = _bullets(_section(text, "Milestones"))
            milestones += _bullets(_section(text, "Active Milestones (Recurring)"))
            milestones += _bullets(_section(text, "Aspirational Milestones (Maturity Gates)"))
            entry["milestones"] = milestones
            entry["excluded"] = _bullets(_section(text, "Excluded Outcomes"))
            entry["directions"] = _bullets(_section(text, "Directions of Travel"))
            entry["practices"] = _bullets(_section(text, "Practices"))

        profiles[nexus] = entry

    # Route selection needs cross-project document frequency: a phrase that
    # appears in most matrices is matrix boilerplate, not a retrieval signal.
    # "M2 - Synthesis and publication plan accepted" retrieves conversations
    # about matrix methodology from every project at once.
    doc_freq = _document_frequency(profiles)
    for entry in profiles.values():
        entry["distinctive_entities"] = _entities(entry, doc_freq, len(profiles))
        entry["routes"] = _routes(entry, doc_freq, len(profiles))
        entry["vocabulary"] = _vocabulary(entry, doc_freq, len(profiles))
    return profiles


def _word_variants(word: str) -> set[str]:
    """The word plus its obvious singular/plural forms.

    The project is "Audio Diaries 1990s"; the conversation says "audio diary
    entries". Without this the name match is lost on the one word that
    identifies the subject.
    """
    forms = {word}
    if word.endswith("ies") and len(word) > 4:
        forms.add(word[:-3] + "y")
    elif word.endswith("es") and len(word) > 4:
        forms.add(word[:-2])
    elif word.endswith("s") and len(word) > 3:
        forms.add(word[:-1])
    else:
        forms.add(word + "s")
    return forms


def _vocabulary(entry: dict, doc_freq: dict[str, int], total: int) -> dict[str, float]:
    """Terms that mark a passage as this project's, weighted by origin.

    Used to aim the excerpt window at the part of a long exchange that made
    it match. Weighting by cross-project frequency alone does not work: with
    only 43 matrices, generic mission language such as "creative", "based"
    and "potential" clears the rarity gate, and four such words outvote the
    one occurrence of "audio diaries" that is the whole point. What a project
    is *about* lives in its name and its distinctive entities; the mission
    prose around them is shared drafting vocabulary.
    """
    weights: dict[str, float] = {}

    name = (entry["name"] or "").strip().lower()
    if len(name.split()) > 1:
        weights[name] = 8.0
    for word in _content_words(name):
        if len(word) >= 4:
            for form in _word_variants(word):
                weights[form] = max(weights.get(form, 0.0), 5.0)

    for phrase in entry.get("distinctive_entities", []):
        cleaned = phrase.strip().lower()
        if len(cleaned) >= 5 and cleaned not in weights:
            weights[cleaned] = 3.0

    # Mission prose contributes only its rarest words, and only as a tiebreak.
    pool = " ".join([entry["core_essence"], entry["resolution"]] + entry["objectives"])
    ceiling = max(1, int(total * 0.12))
    for word in _content_words(pool):
        if len(word) < 5 or doc_freq.get(word, 0) > ceiling:
            continue
        weights.setdefault(word, 1.0)
    return weights


_WORD = re.compile(r"[a-z][a-z0-9'-]{2,}")
_STOP = {
    "the", "and", "for", "that", "with", "this", "from", "are", "was", "not",
    "but", "its", "one", "all", "any", "can", "has", "have", "into", "each",
    "than", "then", "them", "they", "their", "there", "when", "which", "who",
    "will", "would", "been", "being", "over", "under", "more", "most", "some",
    "such", "only", "other", "same", "every", "does", "did", "how", "why",
    "what", "where", "must", "may", "might", "shall", "should", "could",
}


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _document_frequency(profiles: dict[str, dict]) -> dict[str, int]:
    """How many projects' matrix text each word appears in."""
    freq: dict[str, int] = defaultdict(int)
    for entry in profiles.values():
        blob = " ".join(
            [entry["resolution"], entry["core_essence"], entry["name"]]
            + entry["objectives"]
            + entry["milestones"]
            + entry["excluded"]
            + entry["emotional_drivers"]
            + entry.get("directions", [])
            + entry.get("practices", [])
        )
        for word in _content_words(blob):
            freq[word] += 1
    return freq


def _clip(text: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _distinctive(text: str, doc_freq: dict[str, int], total: int) -> list[str]:
    """Content words of ``text`` that are rare across the project set."""
    ceiling = max(2, int(total * 0.25))
    return [w for w in sorted(_content_words(text)) if doc_freq.get(w, 0) <= ceiling]


def _routes(entry: dict, doc_freq: dict[str, int], total: int) -> list[dict]:
    """Independent retrieval routes. Agreement across routes is the signal.

    A route earns its place only if it carries at least two words that are
    rare across the whole project set. Without that gate the milestone and
    constraint boilerplate every matrix shares becomes a majority of the
    routes, they all retrieve the same matrix-methodology conversations, and
    route agreement measures boilerplate rather than subject match.
    """
    candidates: list[dict] = []
    names = " / ".join(entry["aliases"]) or entry["name"]
    candidates.append({"id": "name", "kind": "name", "text": names, "always": True})

    mission = " ".join(b for b in (entry["core_essence"], entry["resolution"]) if b)
    if mission:
        candidates.append({"id": "mission", "kind": "mission", "text": _clip(mission), "always": True})

    for i, objective in enumerate(entry["objectives"], 1):
        candidates.append({"id": f"objective-{i}", "kind": "objective", "text": _clip(objective)})

    drivers = " ".join(entry["emotional_drivers"])
    if drivers:
        candidates.append({"id": "drivers", "kind": "drivers", "text": _clip(drivers)})

    for i, practice in enumerate(entry.get("practices", [])[:6], 1):
        candidates.append({"id": f"practice-{i}", "kind": "practice", "text": _clip(practice, 400)})

    for i, direction in enumerate(entry.get("directions", [])[:6], 1):
        candidates.append({"id": f"direction-{i}", "kind": "direction", "text": _clip(direction, 400)})

    for i, milestone in enumerate(entry["milestones"], 1):
        head = milestone.split(":", 1)[0] if ":" in milestone else milestone
        head = re.sub(r"^M\d+\s*[—-]\s*", "", _clip(head, 300))
        if len(head.split()) >= 3:
            candidates.append({"id": f"milestone-{i}", "kind": "milestone", "text": head})

    entities = entry.get("distinctive_entities") or []
    if len(entities) >= 3:
        candidates.append(
            {"id": "entities", "kind": "entities", "text": ", ".join(entities), "always": True}
        )

    routes: list[dict] = []
    seen: set[str] = set()
    for route in candidates:
        text = route["text"]
        key = text.lower()
        if not key or key in seen:
            continue
        if not route.pop("always", False) and len(_distinctive(text, doc_freq, total)) < 2:
            continue
        seen.add(key)
        routes.append(route)
    return routes


_GENERIC_ENTITY = {
    "Resolution Statement", "Core Essence", "Emotional Drivers", "Working Assumption",
    "Excluded Outcomes", "Objectives", "Milestones", "Constraints", "Evidence",
    "Resolution", "Statement", "Coverage", "Hard", "Soft", "Revisit", "Rationale",
    "Decision", "Date", "Iteration", "Project", "Projects", "Passion", "Matrix",
    "The", "This", "That", "One", "Each", "Every", "Selected", "Accepted",
    "Complete", "Completed", "Directions", "Travel", "Practices", "Spawned",
    "Activity", "Registry", "Toward", "Without", "Within",
}


def _entities(entry: dict, doc_freq: dict[str, int], total: int) -> list[str]:
    """Capitalised terms distinctive to this project, not matrix vocabulary."""
    pool = " ".join(
        [entry["resolution"], entry["core_essence"]]
        + entry["objectives"]
        + entry["milestones"]
        + entry["excluded"]
        + entry.get("directions", [])
        + entry.get("practices", [])
    )
    found = re.findall(r"\b([A-Z][a-zA-Z0-9']+(?:\s+[A-Z][a-zA-Z0-9']+){0,3})\b", pool)
    counts: dict[str, int] = defaultdict(int)
    for term in found:
        if term in _GENERIC_ENTITY or len(term) < 4:
            continue
        if not _distinctive(term, doc_freq, total):
            continue
        counts[term] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    seeded = entry.get("_entity_seed") or []
    return list(dict.fromkeys(seeded + [term for term, _ in ranked]))[:14]


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


def _embed(texts: list[str], provider: str) -> list[list[float]]:
    if provider == "ollama":
        request = urllib.request.Request(
            "http://localhost:11434/api/embed",
            data=json.dumps({"model": "qwen3-embedding:8b-q8_0", "input": texts}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=900) as resp:
            return json.loads(resp.read())["embeddings"]
    from orchestrator import embedding

    return embedding.embed_texts(texts)


def _collection():
    import chromadb
    from orchestrator import embedding

    client = chromadb.PersistentClient(path=str(ORA / "chromadb"))
    return client.get_collection(embedding.resolve_collection("conversations"))


def retrieve(provider: str, per_route: int, out_path: Path, only: list[str] | None = None) -> dict:
    profiles = json.loads((OUT_DIR / "profiles.json").read_text(encoding="utf-8"))
    segments = load_segments()
    collection = _collection()

    index: dict[str, list[tuple[int, int, int]]] = {
        cid: [(s["start_turn"], s["end_turn"], i) for i, s in enumerate(segs)]
        for cid, segs in segments.items()
    }

    resume: dict[str, dict] = {}
    if out_path.exists():
        resume = json.loads(out_path.read_text(encoding="utf-8"))

    for nexus, profile in profiles.items():
        if only and nexus not in only:
            continue
        if nexus in resume and not only:
            continue
        routes = profile["routes"]
        vectors = _embed([r["text"] for r in routes], provider)
        hits: dict[str, dict] = {}
        for route, vector in zip(routes, vectors):
            found = collection.query(
                query_embeddings=[vector],
                n_results=per_route,
                include=["metadatas", "distances"],
            )
            for rank, (meta, distance) in enumerate(
                zip(found["metadatas"][0], found["distances"][0]), 1
            ):
                cid = meta.get("conversation_id")
                turn = meta.get("turn_index")
                if cid not in index or not isinstance(turn, int):
                    continue
                for start, end, seg_i in index[cid]:
                    if not (start <= turn <= end):
                        continue
                    key = f"{cid}#{seg_i}"
                    entry = hits.setdefault(
                        key,
                        {
                            "conversation_id": cid,
                            "segment_index": seg_i,
                            "subject": segments[cid][seg_i]["subject"],
                            "start_turn": start,
                            "end_turn": end,
                            "conversation_title": (meta.get("conversation_title") or "")[:160],
                            "date": meta.get("date") or "",
                            "routes": {},
                            "matched_turns": [],
                            "best_similarity": 0.0,
                            "best_rank": 10**6,
                        },
                    )
                    similarity = 1.0 - float(distance)
                    prior = entry["routes"].get(route["id"])
                    if prior is None or rank < prior["rank"]:
                        entry["routes"][route["id"]] = {
                            "rank": rank,
                            "similarity": round(similarity, 4),
                            "kind": route["kind"],
                        }
                    if turn not in entry["matched_turns"]:
                        entry["matched_turns"].append(turn)
                    entry["best_similarity"] = max(entry["best_similarity"], similarity)
                    entry["best_rank"] = min(entry["best_rank"], rank)
                    break

        for entry in hits.values():
            entry["route_count"] = len(entry["routes"])
            entry["route_kinds"] = sorted({v["kind"] for v in entry["routes"].values()})
            entry["best_similarity"] = round(entry["best_similarity"], 4)
            entry["matched_turns"] = sorted(entry["matched_turns"])[:6]

        # Rank by route agreement, but a segment that is the top hit of any one
        # route is promoted regardless of agreement: the name route is the most
        # specific route a project has and it gets exactly one vote, so pure
        # agreement ordering buries the very hits it exists to find.
        ordered = sorted(
            hits.values(),
            key=lambda e: (-e["route_count"], e["best_rank"], -e["best_similarity"]),
        )
        for entry in ordered:
            entry["route_leader"] = entry["best_rank"] <= 10
        results_entry = {
            "route_total": len(routes),
            "per_route": per_route,
            "candidates": ordered,
        }
        resume[nexus] = results_entry
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(resume, indent=1), encoding="utf-8")
        print(
            f"{nexus:28s} routes={len(routes):2d} segments={len(ordered):5d} "
            f"multi-route={sum(1 for e in ordered if e['route_count'] > 1):5d} "
            f"leaders={sum(1 for e in ordered if e['route_leader']):4d}",
            flush=True,
        )

    return resume


# ---------------------------------------------------------------------------
# judge-input
# ---------------------------------------------------------------------------

_HEAD_CHARS = 250
_WINDOW_CHARS = 900
_WINDOW_STRIDE = 300
_WHOLE_IF_UNDER = 1200
_EXCERPTS_PER_CANDIDATE = 3
_TURNS_PER_CANDIDATE = 5


def _turn_documents(needed: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
    """Fetch the pair text for exactly the turns the judge will read."""
    collection = _collection()
    locator: dict[tuple[str, int], str] = {}
    offset = 0
    while True:
        page = collection.get(limit=5000, offset=offset, include=["metadatas"])
        if not page["ids"]:
            break
        for doc_id, meta in zip(page["ids"], page["metadatas"]):
            key = (meta.get("conversation_id"), meta.get("turn_index"))
            if key in needed:
                locator[key] = doc_id
        offset += len(page["ids"])

    wanted_ids = list(dict.fromkeys(locator.values()))
    texts: dict[str, str] = {}
    for i in range(0, len(wanted_ids), 400):
        chunk = wanted_ids[i : i + 400]
        page = collection.get(ids=chunk, include=["documents"])
        for doc_id, document in zip(page["ids"], page["documents"]):
            texts[doc_id] = document or ""
    return {key: texts.get(doc_id, "") for key, doc_id in locator.items()}


def _body(document: str) -> str:
    """The exchange itself, without the boilerplate context header."""
    body = document.split("## Exchange", 1)[-1].strip()
    return re.sub(r"\s+", " ", body)


def _score_window(window: str, vocabulary: dict[str, float]) -> float:
    """Weighted count of distinct project terms present, on word boundaries."""
    lowered = window.lower()
    tokens = set(_WORD.findall(lowered))
    score = 0.0
    for term, weight in vocabulary.items():
        if not term.isalpha():
            if term in lowered:
                score += weight
        elif term in tokens:
            score += weight
    return score


def _windows(body: str, vocabulary: dict[str, float]) -> list[tuple[float, int, str]]:
    """Every candidate window of one exchange, scored, best first.

    93% of pair bodies are longer than a usable excerpt and the median is
    3,300 characters, so a head-anchored excerpt shows the judge the opening
    of the exchange rather than whatever made it match. One conversation
    matched on a passage about transcribing 1990s audio diaries and the judge
    was shown its opening paragraph about AutoCAD toolbars instead, then
    correctly rejected what it had been given. The window has to follow the
    words.
    """
    if len(body) <= _WHOLE_IF_UNDER:
        return [(_score_window(body, vocabulary), 0, body)]
    scored = []
    for start in range(0, max(1, len(body) - _WINDOW_CHARS + 1), _WINDOW_STRIDE):
        window = body[start : start + _WINDOW_CHARS]
        scored.append((_score_window(window, vocabulary), start, window))
    scored.sort(key=lambda w: (-w[0], w[1]))
    return scored


def _candidate_turns(entry: dict) -> list[int]:
    turns = list(entry["matched_turns"])[: _TURNS_PER_CANDIDATE - 1]
    if entry["start_turn"] not in turns:
        turns.append(entry["start_turn"])
    return sorted(set(turns))[:_TURNS_PER_CANDIDATE]


def build_judge_input(batch_size: int, only: list[str] | None) -> None:
    profiles = json.loads((OUT_DIR / "profiles.json").read_text(encoding="utf-8"))
    candidates = json.loads((OUT_DIR / "candidates.json").read_text(encoding="utf-8"))
    segments = load_segments()

    needed: set[tuple[str, int]] = set()
    for nexus, payload in candidates.items():
        if only and nexus not in only:
            continue
        for entry in payload["candidates"]:
            for turn in _candidate_turns(entry):
                needed.add((entry["conversation_id"], turn))
    print(f"fetching {len(needed)} pair documents ...", flush=True)
    documents = _turn_documents(needed)

    input_root = OUT_DIR / "judge-input"
    input_root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for nexus, payload in candidates.items():
        if only and nexus not in only:
            continue
        profile = profiles[nexus]
        project_block = {
            "nexus": nexus,
            "name": profile["name"],
            "matrix": profile["matrix"],
            "core_essence": profile["core_essence"],
            "resolution_statement": profile["resolution"],
            "objectives": profile["objectives"],
            "excluded_outcomes": profile["excluded"],
            "distinctive_entities": profile.get("distinctive_entities", []),
        }
        vocabulary = profile.get("vocabulary") or {}
        rows = []
        for entry in payload["candidates"]:
            pool: list[tuple[float, int, int, str]] = []
            heads: dict[int, str] = {}
            for turn in _candidate_turns(entry):
                body = _body(documents.get((entry["conversation_id"], turn), ""))
                if not body:
                    continue
                heads[turn] = body[:_HEAD_CHARS]
                for score, offset, window in _windows(body, vocabulary)[:12]:
                    pool.append((score, turn, offset, window))
            pool.sort(key=lambda w: (-w[0], w[1], w[2]))

            picked: list[tuple[float, int, int, str]] = []
            for entry_window in pool:
                if len(picked) >= _EXCERPTS_PER_CANDIDATE:
                    break
                score, turn, offset, _ = entry_window
                # Beyond the first window, only carry passages that actually
                # contain project vocabulary; a zero-scoring third window is
                # an arbitrary slice of the exchange and costs the judge
                # tokens it can do nothing with.
                if picked and score <= 0:
                    break
                if any(
                    other_turn == turn and abs(other_offset - offset) < _WINDOW_CHARS
                    for _, other_turn, other_offset, _ in picked
                ):
                    continue
                picked.append(entry_window)

            picked.sort(key=lambda w: (w[1], w[2]))
            excerpts = []
            for score, turn, offset, window in picked:
                head = heads.get(turn, "")
                text = window if offset == 0 else f"{head} [...] {window}"
                excerpts.append({"turn": turn, "offset": offset, "text": text})
            rows.append(
                {
                    "candidate_id": f"{entry['conversation_id']}#{entry['segment_index']}",
                    "conversation_id": entry["conversation_id"],
                    "segment_index": entry["segment_index"],
                    "subject": entry["subject"],
                    "conversation_title": entry["conversation_title"],
                    "date": entry["date"],
                    "turn_range": [entry["start_turn"], entry["end_turn"]],
                    "matched_routes": sorted(entry["routes"].keys()),
                    "route_count": entry["route_count"],
                    "best_similarity": entry["best_similarity"],
                    "excerpts": excerpts,
                }
            )

        project_dir = input_root / nexus
        project_dir.mkdir(parents=True, exist_ok=True)
        for old in project_dir.glob("batch-*.json"):
            old.unlink()
        for i in range(0, len(rows), batch_size):
            batch_no = i // batch_size + 1
            path = project_dir / f"batch-{batch_no:03d}.json"
            path.write_text(
                json.dumps(
                    {
                        "project": project_block,
                        "batch": batch_no,
                        "expected_candidate_ids": [r["candidate_id"] for r in rows[i : i + batch_size]],
                        "candidates": rows[i : i + batch_size],
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
            manifest.append(
                {"nexus": nexus, "batch": batch_no, "path": str(path), "count": len(rows[i : i + batch_size])}
            )
        print(f"{nexus:28s} candidates={len(rows):5d} batches={(len(rows) + batch_size - 1) // batch_size:3d}", flush=True)

    (OUT_DIR / "judge-manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(m["count"] for m in manifest)
    print(f"\n{total} candidates in {len(manifest)} batches -> {OUT_DIR / 'judge-manifest.json'}")


# ---------------------------------------------------------------------------
# sweep-input
# ---------------------------------------------------------------------------

_SWEEP_WINDOWS = 2
_SWEEP_WINDOW_CHARS = 850


def _spread_excerpts(bodies: list[tuple[int, str]]) -> list[dict]:
    """Excerpts for a segment nothing retrieved, so nothing points at a passage.

    Route-matched candidates get their window aimed by project vocabulary.
    These segments were never matched by any route, so there is no aim to
    take: sample the opening and the middle of the segment's turns instead.
    """
    excerpts: list[dict] = []
    for turn, body in bodies[:_SWEEP_WINDOWS]:
        if len(body) <= _SWEEP_WINDOW_CHARS:
            excerpts.append({"turn": turn, "text": body})
            continue
        head = body[: _SWEEP_WINDOW_CHARS // 2]
        middle_at = max(0, len(body) // 2 - _SWEEP_WINDOW_CHARS // 4)
        middle = body[middle_at : middle_at + _SWEEP_WINDOW_CHARS // 2]
        excerpts.append({"turn": turn, "text": f"{head} [...] {middle}"})
    return excerpts


def _passion_nexuses() -> set[str]:
    """Nexuses whose matrix declares project_type: passion.

    A Passion is an ongoing exploration area with no finite deliverable, so
    what counts as belonging to one differs from a Project: reading and
    tracking a subject is the Passion being lived, not evidence of nothing
    happening.
    """
    found: set[str] = set()
    for path in sorted(MATRIX_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match or not re.search(r"project_type:\s*\n\s*-\s*passion", match.group(1)):
            continue
        for nexus in _frontmatter_nexus(text):
            found.add(nexus)
    return found


def _project_roster(profiles: dict) -> list[dict]:
    return [
        {
            "nexus": nexus,
            "name": profile["name"],
            "about": _clip(profile["core_essence"] or profile["resolution"], 260),
            "objectives": [_clip(o, 160) for o in profile["objectives"][:3]],
        }
        for nexus, profile in sorted(profiles.items())
    ]


def build_sweep_input(kind: str, batch_size: int) -> None:
    """Batches for the segments the project-by-project pass never judged.

    Retrieval asked, for each project, which segments look like it. That
    leaves every segment no project's routes reached unexamined -- 43% of the
    corpus. This asks the opposite question of those segments: given the whole
    project roster, where does this one belong, and does it describe work that
    has no project at all.
    """
    profiles = json.loads((OUT_DIR / "profiles.json").read_text(encoding="utf-8"))
    segments = load_segments()
    accepted_ids: set[str] = set()
    accepted = json.loads((OUT_DIR / "accepted.json").read_text(encoding="utf-8"))["accepted"]
    for rows in accepted.values():
        accepted_ids |= set(rows)
    retrieved: set[str] = set()
    candidates_path = OUT_DIR / "candidates.json"
    if candidates_path.exists():
        for payload in json.loads(candidates_path.read_text(encoding="utf-8")).values():
            for row in payload["candidates"]:
                retrieved.add(f"{row['conversation_id']}#{row['segment_index']}")

    bound_conversations: set[str] = set()
    bindings_path = OUT_DIR / "bindings.json"
    if bindings_path.exists():
        bound_conversations = set(json.loads(bindings_path.read_text(encoding="utf-8")))

    targets: list[tuple[str, int]] = []
    for cid, segs in segments.items():
        for i in range(len(segs)):
            key = f"{cid}#{i}"
            if kind == "unretrieved" and key not in retrieved:
                targets.append((cid, i))
            elif kind == "orphan" and key not in accepted_ids:
                targets.append((cid, i))
            elif kind == "all":
                targets.append((cid, i))
            elif kind == "unbound" and cid not in bound_conversations:
                targets.append((cid, i))
    targets.sort()
    print(f"{kind}: {len(targets)} segments", flush=True)

    needed: set[tuple[str, int]] = set()
    for cid, i in targets:
        seg = segments[cid][i]
        turns = list(range(seg["start_turn"], min(seg["end_turn"], seg["start_turn"] + 3) + 1))
        for turn in turns[:_SWEEP_WINDOWS]:
            needed.add((cid, turn))
    print(f"fetching {len(needed)} pair documents ...", flush=True)
    documents = _turn_documents(needed)

    root = OUT_DIR / f"sweep-input-{kind}"
    if root.exists():
        for old in root.glob("batch-*.json"):
            old.unlink()
    root.mkdir(parents=True, exist_ok=True)

    rows = []
    for cid, i in targets:
        seg = segments[cid][i]
        bodies = []
        for turn in range(seg["start_turn"], min(seg["end_turn"], seg["start_turn"] + 3) + 1):
            body = _body(documents.get((cid, turn), ""))
            if body:
                bodies.append((turn, body))
        if not bodies:
            continue
        rows.append(
            {
                "candidate_id": f"{cid}#{i}",
                "conversation_id": cid,
                "segment_index": i,
                "subject": seg["subject"],
                "turn_range": [seg["start_turn"], seg["end_turn"]],
                "excerpts": _spread_excerpts(bodies),
            }
        )

    roster = _project_roster(profiles)
    if kind == "unbound":
        passion_ids = _passion_nexuses()
        roster = [row for row in roster if row["nexus"] in passion_ids]
        for row in roster:
            entry = profiles[row["nexus"]]
            row["practices"] = [_clip(x, 180) for x in entry.get("practices", [])[:4]]
            row["directions_of_travel"] = [_clip(x, 180) for x in entry.get("directions", [])[:3]]
    manifest = []
    for i in range(0, len(rows), batch_size):
        batch_no = i // batch_size + 1
        chunk = rows[i : i + batch_size]
        path = root / f"batch-{batch_no:03d}.json"
        path.write_text(
            json.dumps(
                {
                    "projects": roster,
                    "batch": batch_no,
                    "expected_candidate_ids": [r["candidate_id"] for r in chunk],
                    "segments": chunk,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        manifest.append({"kind": kind, "batch": batch_no, "path": str(path), "count": len(chunk)})
    (OUT_DIR / f"sweep-manifest-{kind}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(rows)} segments in {len(manifest)} batches -> {root}")


# ---------------------------------------------------------------------------
# verify-input
# ---------------------------------------------------------------------------

_REASON_STOP = set(
    """the and for that with this from are was not but its one all any can has have
    into each than then them they their there when which who will would been being
    over under more most some such only other same every does did how why what where
    must may might shall should could about your you our project projects discussion
    mention direct content related engagement segment""".split()
)


def _reason_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 4 and w not in _REASON_STOP}


def build_verify_input(batch_size: int) -> None:
    """Re-judge accepted candidates whose reason does not describe them.

    A judge working through 80 candidates can drift into writing one batch's
    summary into every candidate's reason field: a political-satire segment
    was accepted for the golf passion with the reason "Golf swing
    biomechanics and technique analysis", which is a different candidate's
    sentence. The verdict may still be right, but nothing in the record shows
    it was reached on this candidate, so it is re-judged one at a time.
    """
    accepted = json.loads((OUT_DIR / "accepted.json").read_text(encoding="utf-8"))["accepted"]
    profiles = json.loads((OUT_DIR / "profiles.json").read_text(encoding="utf-8"))

    candidates: dict[tuple[str, str], dict] = {}
    for path in (OUT_DIR / "judge-input").glob("*/batch-*.json"):
        nexus = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("candidates", []):
            candidates[(nexus, row["candidate_id"])] = row

    root = OUT_DIR / "verify-input"
    if root.exists():
        for old in root.glob("*/batch-*.json"):
            old.unlink()
    root.mkdir(parents=True, exist_ok=True)

    manifest = []
    for nexus, rows in sorted(accepted.items()):
        suspect = []
        for candidate_id, verdict in rows.items():
            row = candidates.get((nexus, candidate_id))
            if row is None:
                continue
            reason = _reason_words(verdict.get("reason", ""))
            if not reason:
                suspect.append(row)
                continue
            described = _reason_words(
                row["subject"] + " " + " ".join(e["text"] for e in row["excerpts"])
            )
            if not (reason & described):
                suspect.append(row)
        if not suspect:
            continue
        profile = profiles[nexus]
        block = {
            "nexus": nexus,
            "name": profile["name"],
            "core_essence": profile["core_essence"],
            "resolution_statement": profile["resolution"],
            "objectives": profile["objectives"],
            "excluded_outcomes": profile["excluded"],
            "distinctive_entities": profile.get("distinctive_entities", []),
        }
        project_dir = root / nexus
        project_dir.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(suspect), batch_size):
            batch_no = i // batch_size + 1
            path = project_dir / f"batch-{batch_no:03d}.json"
            chunk = suspect[i : i + batch_size]
            path.write_text(
                json.dumps(
                    {
                        "project": block,
                        "batch": batch_no,
                        "expected_candidate_ids": [r["candidate_id"] for r in chunk],
                        "candidates": chunk,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
            manifest.append({"nexus": nexus, "batch": batch_no, "path": str(path), "count": len(chunk)})
        print(f"{nexus:26s} re-judging {len(suspect):4d} of {len(rows):4d}")

    (OUT_DIR / "verify-manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(m["count"] for m in manifest)
    print(f"\n{total} candidates in {len(manifest)} verification batches")


# ---------------------------------------------------------------------------
# discovery-consolidate
# ---------------------------------------------------------------------------


def _title_key(title: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    words = [w for w in text.split() if w not in {"the", "a", "an", "of", "and", "for", "book", "novel", "paper", "project", "report", "series"}]
    return " ".join(sorted(set(words)))


_TYPE_WORDS = {
    "book", "books", "novel", "novels", "paper", "papers", "project", "projects",
    "framework", "frameworks", "series", "report", "reports", "system", "systems",
    "guide", "article", "articles", "essay", "essays", "memoir", "manuscript",
    "outline", "white", "whitepaper", "platform", "tool", "suite", "the", "a",
    "an", "of", "and", "for", "on", "in", "to", "with", "my", "new",
}


def _probes(title: str) -> list[str]:
    """Distinctive substrings to look for a work by.

    The full title is the wrong probe. A discovery agent writes "DIKLIS
    CHUMP: Loser Legacy" or "Wobble Model: Classical Explanation for Quantum
    Phenomena"; neither string is in the vault, while "Diklis Chump" and
    "Wobble Model" are all over it. Leading type words are wrong too: probing
    "Book on Assisted Human Intelligence" as "Book on Assisted" misses the
    "Assisted Human Intelligence" paper that already documents it.
    """
    text = (title or "").strip()
    if not text:
        return []
    head = re.split(r"[:(\u2014\u2013]", text)[0].strip()
    words = re.findall(r"[A-Za-z][A-Za-z0-9'`]*", head)
    while words and words[0].lower() in _TYPE_WORDS:
        words.pop(0)
    named = [w for w in words if w.lower() not in _TYPE_WORDS]

    probes = set()
    if len(text) >= 6:
        probes.add(text)
    if len(head) >= 6:
        probes.add(head)
    for size in (4, 3, 2):
        if len(named) >= size:
            probes.add(" ".join(named[:size]))
    if len(named) == 1 and len(named[0]) >= 4:
        probes.add(named[0])
    return sorted({p for p in probes if len(p) >= 4}, key=len, reverse=True)


def _known_names() -> dict[str, str]:
    """Project display names and Incubator artifact titles, for exact matching."""
    known: dict[str, str] = {}
    for path in sorted(PROJECT_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for value in (record.get("display_name"), record.get("name"), record.get("folder_name")):
            if isinstance(value, str) and len(value) >= 4:
                known.setdefault(value.lower(), f"project: {value}")
    incubator = VAULT / "Projects" / "Incubator"
    if incubator.is_dir():
        for path in sorted(incubator.glob("*.md")):
            stem = re.sub(r"^Book \u2014 ", "", path.stem)
            stem = re.sub(r"\s+(Book\s+)?Report$|\s+Outline$", "", stem).strip()
            if len(stem) >= 4:
                known.setdefault(stem.lower(), f"incubator: {path.name}")
    return known


# Where the vault documents a work. Archive/ holds 135k raw atomics and
# Resources/ holds harvested source material; a title appearing there is
# evidence the subject was discussed, not that the work is documented. Adding
# them also makes the search unusable: one fixed-string pass over the whole
# vault is 233k files and returns more matches than can be held in memory.
_DOCUMENTED_IN = ("Matrix", "Projects", "Modes", "Lenses")


def _vault_probe_hits(all_probes: set[str]) -> dict[str, list[str]]:
    """Look every probe up in the vault's documentation areas in one pass.

    Done in-process rather than by grep: BSD grep given a pattern file of
    several hundred fixed strings degrades to minutes over even this small a
    tree, while the same search in memory is a couple of seconds. The
    documentation areas are ~1,700 files, so reading them costs nothing.
    """
    if not all_probes:
        return {}
    hits: dict[str, list[str]] = {p: [] for p in all_probes}
    lowered = [(p, p.lower()) for p in sorted(all_probes)]
    roots = [VAULT / name for name in _DOCUMENTED_IN if (VAULT / name).is_dir()]
    files = [f for root in roots for f in root.rglob("*.md")]
    files.extend(VAULT.glob("*.md"))
    for path in files:
        try:
            body = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        rel = str(path)[len(str(VAULT)) + 1 :]
        for probe, needle in lowered:
            if needle in body and len(hits[probe]) < 6:
                hits[probe].append(rel)
    return hits


def discovery_consolidate() -> None:
    """Cluster the discovered works, then ask the vault whether it knows them.

    The discovery agents were given the project roster and the Incubator's
    titles, but a work can already be documented under a name the agent did
    not recognise -- "The Supreme Chumps" is inside the Supreme Court book
    report, and "Hector Rentier" is a Main Street Independent voice. Only the
    vault can settle that, so every candidate title is looked up in it.
    """
    works: list[dict] = []
    unreadable = 0
    for path in sorted((OUT_DIR / "discovery-output").glob("batch-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            unreadable += 1
            continue
        for work in payload.get("works", []):
            work["batch"] = payload.get("batch")
            works.append(work)

    real_segments: set[str] = set()
    for cid, segs in load_segments().items():
        for i in range(len(segs)):
            real_segments.add(f"{cid}#{i}")

    clusters: dict[str, dict] = {}
    invented_evidence = 0
    for work in works:
        key = _title_key(work.get("title", ""))
        if not key:
            continue
        evidence = [e for e in work.get("evidence_ids", []) if isinstance(e, str)]
        good = [e for e in evidence if e in real_segments]
        invented_evidence += len(evidence) - len(good)
        entry = clusters.setdefault(
            key,
            {
                "titles": [], "kinds": [], "descriptions": [], "quotes": [],
                "development": [], "evidence_ids": [], "duplicate_of": [], "mentions": 0,
            },
        )
        entry["mentions"] += 1
        entry["titles"].append(work.get("title", ""))
        entry["kinds"].append(work.get("kind", ""))
        entry["descriptions"].append(work.get("description", ""))
        if work.get("quote"):
            entry["quotes"].append(work["quote"])
        entry["development"].append(work.get("development", ""))
        entry["evidence_ids"].extend(good)
        if (work.get("possible_duplicate_of") or "").strip():
            entry["duplicate_of"].append(work["possible_duplicate_of"].strip())

    rank = {"advanced": 3, "moderate": 2, "early": 1, "passing": 0}
    rows = []
    for key, entry in clusters.items():
        title = max(entry["titles"], key=len)
        rows.append(
            {
                "title": title,
                "key": key,
                "kind": collections.Counter(entry["kinds"]).most_common(1)[0][0],
                "development": max(entry["development"], key=lambda d: rank.get(d, 0)),
                "mentions": entry["mentions"],
                "description": max(entry["descriptions"], key=len),
                "quote": max(entry["quotes"], key=len) if entry["quotes"] else "",
                "evidence_ids": sorted(set(entry["evidence_ids"]))[:12],
                "evidence_count": len(set(entry["evidence_ids"])),
                "agent_duplicate_of": sorted(set(entry["duplicate_of"])),
                "probes": _probes(title),
            }
        )
    known = _known_names()
    hits = _vault_probe_hits({p for row in rows for p in row["probes"]})
    for row in rows:
        seen: list[str] = []
        matched: list[str] = []
        for probe in row["probes"]:
            if hits.get(probe):
                matched.append(probe)
                for path in hits[probe]:
                    if path not in seen:
                        seen.append(path)
        row["vault_mentions"] = seen[:6]
        row["matched_probes"] = matched
        row["known_as"] = ""
        for probe in row["probes"]:
            match = known.get(probe.lower())
            if match:
                row["known_as"] = match
                break
    rows.sort(key=lambda r: (-rank.get(r["development"], 0), -r["evidence_count"], r["title"]))
    (OUT_DIR / "discovered-works.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    undocumented = [r for r in rows if not r["vault_mentions"] and not r["known_as"]]
    print(f"works reported {len(works)}  clusters {len(rows)}  unreadable batches {unreadable}")
    print(f"evidence ids that are not real segments: {invented_evidence}")
    print(f"clusters with no vault mention at all: {len(undocumented)}")
    print()
    for row in undocumented[:40]:
        print(f"  [{row['development']:8s} {row['kind']:12s} ev={row['evidence_count']:2d}] {row['title'][:70]}")


# ---------------------------------------------------------------------------
# sweep-collect
# ---------------------------------------------------------------------------


def sweep_collect(kind: str = "unretrieved") -> dict:
    """Fold the roster sweep's placements into the accepted set.

    Retrieval asked each project which segments look like it, which serves a
    named project with distinctive vocabulary far better than a Passion whose
    matrix is three short generic sentences. The sweep asks each unexamined
    segment where it belongs, and the Passions are where the difference lands.
    """
    profiles = json.loads((OUT_DIR / "profiles.json").read_text(encoding="utf-8"))
    valid = set(profiles)
    segments = load_segments()
    real = set(segments)

    accepted_path = OUT_DIR / "accepted.json"
    data = json.loads(accepted_path.read_text(encoding="utf-8"))
    accepted = {k: dict(v) for k, v in data["accepted"].items()}

    inputs: dict[str, dict] = {}
    for path in (OUT_DIR / f"sweep-input-{kind}").glob("batch-*.json"):
        for row in json.loads(path.read_text(encoding="utf-8"))["segments"]:
            inputs[row["candidate_id"]] = row

    stats = {
        "answered": 0,
        "placed": 0,
        "memberships": 0,
        "invalid_nexus": 0,
        "unknown_candidate": 0,
        "unreadable_batches": 0,
    }
    for path in sorted((OUT_DIR / f"sweep-output-{kind}").glob("batch-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats["unreadable_batches"] += 1
            print(f"unreadable: {path.name}")
            continue
        for placement in payload.get("placements", []):
            candidate_id = placement.get("candidate_id")
            row = inputs.get(candidate_id)
            if row is None:
                stats["unknown_candidate"] += 1
                continue
            if row["conversation_id"] not in real:
                stats["unknown_candidate"] += 1
                continue
            stats["answered"] += 1
            nexuses = [n for n in placement.get("nexuses", []) if isinstance(n, str)]
            stats["invalid_nexus"] += len([n for n in nexuses if n not in valid])
            nexuses = [n for n in nexuses if n in valid]
            if not nexuses:
                continue
            stats["placed"] += 1
            for nexus in dict.fromkeys(nexuses):
                stats["memberships"] += 1
                accepted.setdefault(nexus, {})[candidate_id] = {
                    "conversation_id": row["conversation_id"],
                    "segment_index": row["segment_index"],
                    "subject": row["subject"],
                    "conversation_title": "",
                    "date": "",
                    "route_count": 0,
                    "best_similarity": 0.0,
                    "confidence": str(placement.get("confidence", "")).strip().lower(),
                    "reason": str(placement.get("reason", ""))[:200],
                    "source": f"sweep-{kind}",
                }

    data["accepted"] = {k: v for k, v in sorted(accepted.items())}
    data["stats"]["sweep"] = stats
    accepted_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))
    for nexus, rows in sorted(accepted.items()):
        swept = sum(1 for r in rows.values() if str(r.get("source", "")).startswith("sweep"))
        print(f"{nexus:26s} segments={len(rows):5d}  (+{swept} from sweep)")
    return data


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


def collect(strict: bool) -> dict:
    """Validate every judge output file and assemble the accepted set.

    Agents fabricate. A prior run of this campaign had seven conversation ids
    invented outright, so nothing here is trusted: every returned candidate_id
    must appear in the batch's own expected list, every expected id must have
    a verdict, and every conversation id must exist in the real corpus before
    it can be bound.
    """
    manifest = json.loads((OUT_DIR / "judge-manifest.json").read_text(encoding="utf-8"))
    output_root = OUT_DIR / "judge-output"
    real_conversations = set(load_segments())

    # A re-judgement of an accept whose recorded reason did not describe it
    # replaces the original verdict. 55% of those were overturned on a
    # second, single-candidate reading, so they are not a rounding error.
    overrides: dict[tuple[str, str], str] = {}
    for path in (OUT_DIR / "verify-output").glob("*/batch-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for verdict in data.get("verdicts", []):
            candidate_id = verdict.get("candidate_id")
            if isinstance(candidate_id, str):
                overrides[(path.parent.name, candidate_id)] = str(
                    verdict.get("verdict", "")
                ).strip().lower()
    stats_overridden = 0

    accepted: dict[str, dict[str, dict]] = defaultdict(dict)
    problems: list[dict] = []
    stats = {
        "batches_expected": len(manifest),
        "batches_present": 0,
        "verdicts": 0,
        "accepted": 0,
        "fabricated_ids": 0,
        "unjudged_ids": 0,
        "verified_overrides": 0,
    }

    for item in manifest:
        nexus, batch = item["nexus"], item["batch"]
        source = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
        expected = list(source["expected_candidate_ids"])
        expected_set = set(expected)
        by_id = {c["candidate_id"]: c for c in source["candidates"]}

        out_path = output_root / nexus / f"batch-{batch:03d}.json"
        if not out_path.exists():
            problems.append({"nexus": nexus, "batch": batch, "issue": "missing output"})
            continue
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append({"nexus": nexus, "batch": batch, "issue": f"unreadable: {exc}"})
            continue
        verdicts = data.get("verdicts")
        if not isinstance(verdicts, list):
            problems.append({"nexus": nexus, "batch": batch, "issue": "no verdicts list"})
            continue

        stats["batches_present"] += 1
        seen: set[str] = set()
        fabricated: list[str] = []
        for verdict in verdicts:
            cid = verdict.get("candidate_id")
            if cid not in expected_set:
                fabricated.append(str(cid))
                continue
            if cid in seen:
                continue
            seen.add(cid)
            stats["verdicts"] += 1
            decision = str(verdict.get("verdict", "")).strip().lower()
            override = overrides.get((nexus, cid))
            if override is not None and override != decision:
                stats_overridden += 1
                decision = override
            if decision != "yes":
                continue
            row = by_id[cid]
            if row["conversation_id"] not in real_conversations:
                fabricated.append(cid)
                continue
            stats["accepted"] += 1
            accepted[nexus][cid] = {
                "conversation_id": row["conversation_id"],
                "segment_index": row["segment_index"],
                "subject": row["subject"],
                "conversation_title": row["conversation_title"],
                "date": row["date"],
                "route_count": row["route_count"],
                "best_similarity": row["best_similarity"],
                "confidence": str(verdict.get("confidence", "")).strip().lower(),
                "reason": str(verdict.get("reason", ""))[:200],
            }

        unjudged = [e for e in expected if e not in seen]
        if fabricated:
            stats["fabricated_ids"] += len(fabricated)
            problems.append(
                {"nexus": nexus, "batch": batch, "issue": f"{len(fabricated)} ids not in batch",
                 "sample": fabricated[:5]}
            )
        if unjudged:
            stats["unjudged_ids"] += len(unjudged)
            problems.append(
                {"nexus": nexus, "batch": batch, "issue": f"{len(unjudged)} expected ids unjudged",
                 "sample": unjudged[:5]}
            )

    stats["verified_overrides"] = stats_overridden
    result = {
        "stats": stats,
        "problems": problems,
        "accepted": {k: v for k, v in sorted(accepted.items())},
    }
    (OUT_DIR / "accepted.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

    for nexus in sorted(accepted):
        rows = accepted[nexus]
        conversations = {r["conversation_id"] for r in rows.values()}
        print(f"{nexus:28s} segments={len(rows):5d} conversations={len(conversations):5d}")
    print()
    print(json.dumps(stats, indent=1))
    if problems:
        print(f"\n{len(problems)} problem batches (first 20):")
        for problem in problems[:20]:
            print(" ", json.dumps(problem))
        incomplete = sorted({(p["nexus"], p["batch"]) for p in problems})
        (OUT_DIR / "rerun-batches.json").write_text(
            json.dumps([{"nexus": n, "batch": b} for n, b in incomplete], indent=1), encoding="utf-8"
        )
        print(f"\n-> {len(incomplete)} batches listed in rerun-batches.json")
        if strict:
            raise SystemExit(1)
    return result


# ---------------------------------------------------------------------------
# bind
# ---------------------------------------------------------------------------


def bind(apply_changes: bool, min_confidence: str) -> None:
    """Write conversation -> project membership through conversation_memory."""
    from orchestrator import conversation_memory

    data = json.loads((OUT_DIR / "accepted.json").read_text(encoding="utf-8"))
    rank = {"high": 3, "medium": 2, "low": 1, "": 0}
    floor = rank.get(min_confidence, 0)
    real_conversations = set(load_segments())

    memberships: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, str] = {}
    evidence: dict[str, list[dict]] = defaultdict(list)
    for nexus, rows in data["accepted"].items():
        for row in rows.values():
            if rank.get(row["confidence"], 0) < floor:
                continue
            cid = row["conversation_id"]
            if cid not in real_conversations:
                continue
            memberships[cid].add(nexus)
            titles.setdefault(cid, (row["conversation_title"] or row["subject"] or cid).strip())
            evidence[cid].append({"nexus": nexus, "segment": row["segment_index"], "subject": row["subject"]})

    counts = defaultdict(int)
    for nexuses in memberships.values():
        counts[len(nexuses)] += 1
    per_project = defaultdict(int)
    for nexuses in memberships.values():
        for nexus in nexuses:
            per_project[nexus] += 1

    print(f"conversations with at least one project: {len(memberships)} of {len(real_conversations)}")
    print("memberships per conversation:", dict(sorted(counts.items())))
    print()
    for nexus, total in sorted(per_project.items(), key=lambda kv: -kv[1]):
        print(f"{nexus:28s} conversations={total:5d}")

    report = {
        "conversations": len(memberships),
        "per_project": dict(sorted(per_project.items())),
        "membership_histogram": dict(sorted(counts.items())),
        "min_confidence": min_confidence,
    }
    (OUT_DIR / "bind-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (OUT_DIR / "bindings.json").write_text(
        json.dumps(
            {cid: {"projects": sorted(v), "title": titles[cid], "evidence": evidence[cid]}
             for cid, v in sorted(memberships.items())},
            indent=1,
        ),
        encoding="utf-8",
    )

    if not apply_changes:
        print("\ndry run - nothing written. Re-run with --apply to bind.")
        return

    written = 0
    failed: list[str] = []
    for cid, nexuses in sorted(memberships.items()):
        path = conversation_memory.set_conversation_projects(
            cid,
            sorted(nexuses),
            create_if_missing=True,
            display_name=titles[cid][:120],
        )
        if path is None:
            failed.append(cid)
        else:
            written += 1
    print(f"\nbound {written} conversations; {len(failed)} failed")
    if failed:
        print("failed sample:", failed[:10])
        (OUT_DIR / "bind-failures.json").write_text(json.dumps(failed, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# hydrate
# ---------------------------------------------------------------------------

_ARCHIVE_USER = re.compile(r"^###\s+User input\s*$", re.M)
_ARCHIVE_ASSISTANT = re.compile(r"^###\s+Assistant response\s*$", re.M)
_ARCHIVE_TIMESTAMP = re.compile(r"^source_timestamp:\s*(\S+)\s*$", re.M)
_ARCHIVE_DATE = re.compile(r"^date created:\s*(\S+)\s*$", re.M)
_FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})")


def _archive_timestamp(text: str, path: Path) -> str:
    """When this pair happened, from the file's own front matter.

    Without a timestamp on the messages the interface cannot date these
    conversations: iter_conversations derives last_activity_at from the most
    recent message that carries one, so undated imports sort below everything
    and show no date at all.
    """
    match = _ARCHIVE_TIMESTAMP.search(text)
    if match:
        return match.group(1)
    match = _FILENAME_DATE.search(path.name)
    if match:
        return f"{match.group(1)}T{match.group(2)}:{match.group(3)}:00"
    match = _ARCHIVE_DATE.search(text)
    return f"{match.group(1)}T00:00:00" if match else ""


def _parse_archive_pair(text: str) -> tuple[str, str]:
    """Split one archived pair file into its user and assistant halves.

    The assistant half runs to the END OF FILE. Model responses carry their
    own headings at every level -- "## NARRATIVE RECAP", "## Bottom Line",
    "### Scene Architecture" -- and stopping at any of them truncates the
    answer mid-thought. Stopping at the next H2 silently cut 31% of pairs,
    some to 7% of their length, right where a heading draws its rule across
    the page. Nothing structural follows the assistant section: across 3,000
    sampled files the last H2 after it takes 769 distinct values, all of them
    content ("Bottom Line", "Conclusion", "Summary"), with no shared trailer.

    Each heading appears exactly once per file, so the user half is bounded
    by the assistant heading with no ambiguity. Either half may legitimately
    be empty -- about 9% of archived pairs have one side blank -- and an empty
    half is dropped rather than written as an empty message.
    """
    marker = text.find("## Exchange")
    if marker < 0:
        return "", ""
    body = text[marker + len("## Exchange") :]
    user_match = _ARCHIVE_USER.search(body)
    assistant_match = _ARCHIVE_ASSISTANT.search(body)
    if not user_match or not assistant_match:
        return "", ""
    user = body[user_match.end() : assistant_match.start()].strip()
    assistant = body[assistant_match.end() :].strip()
    return user, assistant


def _archive_locations() -> dict[str, list[tuple[int, str]]]:
    """conversation_id -> [(turn_index, archive file path)], in turn order.

    The vector index is the only thing that knows which archive files make up
    a conversation; the files themselves are one pair each and carry no
    conversation id.
    """
    collection = _collection()
    found: dict[str, dict[int, str]] = defaultdict(dict)
    offset = 0
    while True:
        page = collection.get(limit=5000, offset=offset, include=["metadatas"])
        if not page["ids"]:
            break
        for meta in page["metadatas"]:
            cid = meta.get("conversation_id")
            turn = meta.get("turn_index")
            path = meta.get("obsidian_path") or meta.get("chunk_path") or ""
            if isinstance(cid, str) and isinstance(turn, int) and path:
                found[cid].setdefault(turn, path)
        offset += len(page["ids"])
    return {cid: sorted(turns.items()) for cid, turns in found.items()}


def hydrate(apply_changes: bool, limit: int | None) -> None:
    """Fill each bound archive conversation's envelope with its actual turns.

    Binding gave these conversations identity and project membership but left
    ``messages`` empty, because their turns live in the markdown archive and
    the vector index rather than in the envelope. That is enough to file a
    conversation and not enough to read one: the interface renders the
    envelope, so a filed conversation opened as a blank shell.
    """
    from orchestrator import conversation_memory

    bindings = json.loads((OUT_DIR / "bindings.json").read_text(encoding="utf-8"))
    # Every archived conversation, not only the ones that earned a project.
    # A conversation under no project is Commons, not nonexistent, and
    # without an envelope it cannot be opened or found at all.
    targets = sorted(load_segments())
    print(f"locating archive files for {len(targets)} conversations ...", flush=True)
    locations = _archive_locations()

    stats = {
        "conversations": 0,
        "envelopes_created": 0,
        "already_populated": 0,
        "no_archive_files": 0,
        "missing_files": 0,
        "unparsed_files": 0,
        "messages": 0,
        "written": 0,
        "failed": 0,
    }
    empty_after: list[str] = []
    for count, cid in enumerate(targets):
        if limit and count >= limit:
            break
        stats["conversations"] += 1
        if cid not in bindings and conversation_memory.load_conversation_json(cid) is None:
            created = conversation_memory.ensure_conversation_envelope(
                cid, project_ids=[], display_name="", sessions_root=conversation_memory._DEFAULT_SESSIONS_ROOT
            )
            if created is None:
                stats["failed"] += 1
                continue
            stats["envelopes_created"] += 1
        pairs = locations.get(cid) or []
        if not pairs:
            stats["no_archive_files"] += 1
            continue

        messages: list[dict[str, Any]] = []
        for turn, path in pairs:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                stats["missing_files"] += 1
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                stats["missing_files"] += 1
                continue
            user, assistant = _parse_archive_pair(text)
            if not user and not assistant:
                stats["unparsed_files"] += 1
                continue
            stamp = _archive_timestamp(text, file_path)
            if user:
                entry = {"role": "user", "content": user, "turn": turn}
                if stamp:
                    entry["timestamp"] = stamp
                messages.append(entry)
            if assistant:
                entry = {"role": "assistant", "content": assistant, "turn": turn}
                if stamp:
                    entry["timestamp"] = stamp
                messages.append(entry)

        if not messages:
            empty_after.append(cid)
            continue
        stats["messages"] += len(messages)

        if not apply_changes:
            continue

        latest = ""
        for entry in messages:
            stamp = entry.get("timestamp") or ""
            if stamp > latest:
                latest = stamp

        def fill(data: dict[str, Any], _messages=messages, _latest=latest) -> None:
            if data.get("messages"):
                raise _AlreadyPopulated
            data["messages"] = _messages
            # Mark imported history as read. The unread rule is "has an
            # assistant turn and no read timestamp", so dating these without
            # this would move all of them into Unread at once -- 3,132
            # conversations the user lived through years ago, presented as
            # waiting for attention.
            if _latest and not data.get("last_read_at"):
                data["last_read_at"] = _latest
            if not (data.get("display_name") or "").strip():
                for entry in _messages:
                    if entry.get("role") == "user" and entry.get("content"):
                        data["display_name"] = " ".join(entry["content"].split())[:120]
                        break

        try:
            written = conversation_memory._mutate_conversation_envelope(
                cid, conversation_memory._DEFAULT_SESSIONS_ROOT, fill
            )
        except _AlreadyPopulated:
            stats["already_populated"] += 1
            continue
        if written is None:
            stats["failed"] += 1
        else:
            stats["written"] += 1
        if stats["written"] and stats["written"] % 250 == 0:
            print(f"  {stats['written']} written ...", flush=True)

    print(json.dumps(stats, indent=1))
    if empty_after:
        print(f"conversations that yielded no readable turns: {len(empty_after)}")
        print("  " + ", ".join(empty_after[:8]))
    if not apply_changes:
        print("\ndry run - nothing written. Re-run with --apply.")


class _AlreadyPopulated(Exception):
    """Raised to abandon a mutation rather than overwrite a real conversation."""


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("profiles", help="build retrieval profiles from matrices")

    p_ret = sub.add_parser("retrieve", help="multi-route vector retrieval")
    p_ret.add_argument("--provider", choices=["ollama", "configured"], default="configured")
    p_ret.add_argument("--per-route", type=int, default=300)
    p_ret.add_argument("--out", default=str(OUT_DIR / "candidates.json"))
    p_ret.add_argument("--only", nargs="*", help="re-run just these nexuses")

    p_judge = sub.add_parser("judge-input", help="write per-batch agent input files")
    p_judge.add_argument("--batch-size", type=int, default=80)
    p_judge.add_argument("--only", nargs="*")

    p_sweep = sub.add_parser("sweep-input", help="batches for segments the project pass never judged")
    p_sweep.add_argument("--kind", choices=["unretrieved", "orphan", "all", "unbound"], default="unretrieved")
    p_sweep.add_argument("--batch-size", type=int, default=40)

    p_verify = sub.add_parser("verify-input", help="re-judge accepts whose reason does not describe them")
    p_verify.add_argument("--batch-size", type=int, default=40)

    sub.add_parser("discovery-consolidate", help="cluster discovered works and check them against the vault")

    p_sc = sub.add_parser("sweep-collect", help="fold roster-sweep placements into the accepted set")
    p_sc.add_argument("--kind", choices=["unretrieved", "orphan", "all", "unbound"], default="unretrieved")

    p_collect = sub.add_parser("collect", help="validate judge output and assemble accepted set")
    p_collect.add_argument("--strict", action="store_true", help="exit non-zero if any batch is bad")

    p_hydrate = sub.add_parser("hydrate", help="fill bound archive envelopes with their real turns")
    p_hydrate.add_argument("--apply", action="store_true")
    p_hydrate.add_argument("--limit", type=int)

    p_bind = sub.add_parser("bind", help="write conversation project membership")
    p_bind.add_argument("--apply", action="store_true")
    p_bind.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")

    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "profiles":
        profiles = build_profiles()
        path = OUT_DIR / "profiles.json"
        path.write_text(json.dumps(profiles, indent=1), encoding="utf-8")
        for nexus, profile in sorted(profiles.items()):
            print(
                f"{nexus:28s} matrix={'yes' if profile['matrix'] else 'NO ':4s} "
                f"routes={len(profile['routes']):2d} "
                f"obj={len(profile['objectives']):2d} ms={len(profile['milestones']):2d}"
            )
        print(f"\n{len(profiles)} profiles -> {path}")
        return 0

    if args.command == "sweep-input":
        build_sweep_input(args.kind, args.batch_size)
        return 0

    if args.command == "verify-input":
        build_verify_input(args.batch_size)
        return 0

    if args.command == "discovery-consolidate":
        discovery_consolidate()
        return 0

    if args.command == "sweep-collect":
        sweep_collect(args.kind)
        return 0

    if args.command == "collect":
        collect(args.strict)
        return 0

    if args.command == "hydrate":
        hydrate(args.apply, args.limit)
        return 0

    if args.command == "bind":
        bind(args.apply, args.min_confidence)
        return 0

    if args.command == "judge-input":
        build_judge_input(args.batch_size, args.only)
        return 0

    if args.command == "retrieve":
        retrieve(args.provider, args.per_route, Path(args.out), args.only)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
