#!/usr/bin/env python3
"""Associate archived conversation segments with registered projects.

One script, four subcommands, run in order:

    profiles    matrices + project records -> one retrieval profile per project
    retrieve    multi-route vector retrieval -> segment-level candidates
    bind        judged verdicts -> conversation project membership

The judgment pass between ``retrieve`` and ``bind`` runs as Claude Code
subagents (the user's subscription), not through Ora's model dispatch; this
script writes the agent input files and reads the agent verdict files back.

Every stage persists to ``data/conversation-projects/`` so a run interrupted
by a session limit resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
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

    accepted: dict[str, dict[str, dict]] = defaultdict(dict)
    problems: list[dict] = []
    stats = {
        "batches_expected": len(manifest),
        "batches_present": 0,
        "verdicts": 0,
        "accepted": 0,
        "fabricated_ids": 0,
        "unjudged_ids": 0,
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
            if str(verdict.get("verdict", "")).strip().lower() != "yes":
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

    p_collect = sub.add_parser("collect", help="validate judge output and assemble accepted set")
    p_collect.add_argument("--strict", action="store_true", help="exit non-zero if any batch is bad")

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

    if args.command == "collect":
        collect(args.strict)
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
