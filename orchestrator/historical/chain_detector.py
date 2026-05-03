"""Chain detection for historical sessions (Phase 2B).

A SESSION is one chat from start to finish — one source `.md` file in
`~/Documents/conversations/raw/` that produced N cleaned-pair files.

A CHAIN is a group of related sessions that build on each other across
weeks or months — e.g. all the Claude/ChatGPT/Gemini sessions you ran
while drafting the American Jesus narrative are one chain.

Two methods detect chain membership; both must agree only if you tighten
thresholds, but by default an edge between sessions exists if EITHER
method matches:

  Method 1 — title-keyword overlap.
    Distinctive keywords pulled from the session's source filename
    (after stripping platform prefix, date, and stop-words). Two
    sessions are linked if their keyword sets share at least
    `min_shared_title_keywords` distinctive terms.

  Method 2 — topic-fingerprint overlap.
    Capitalized noun phrases pulled from the session's aggregated
    cleaned content (using the same extractor the vault indexer uses,
    `extract_key_phrases`). Two sessions are linked if their phrase
    sets share at least `min_shared_phrases` terms.

Sessions form a graph; chains are the connected components. Each chain
gets a stable `chain_id` (SHA-256 of sorted session-ids, truncated) and
a human-readable `chain_label` (the most common shared keyword/phrase
across its sessions).

Chain detection writes its result to `~/ora/data/chain-index.json` so
downstream phases can look up chain membership without recomputing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from orchestrator.tools.vault_indexer import (
    extract_key_phrases,
    topic_fingerprint,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

CHAIN_INDEX_DEFAULT = "/Users/oracle/ora/data/chain-index.json"

# Method 1 — title-keyword sensitivity
DEFAULT_MIN_SHARED_TITLE_KEYWORDS = 2   # ≥ 2 distinctive keywords in common
# Method 2 — topic-fingerprint sensitivity. 4 chosen empirically — at 3
# the 3,486-session test corpus produced a 1,000+ session chain via
# transitive linking on moderately-common phrases.
DEFAULT_MIN_SHARED_PHRASES        = 4
# How many key phrases to extract per session (more = better recall, slower)
DEFAULT_PHRASES_PER_SESSION       = 12

# A term is "distinctive" if it appears in fewer than this fraction of all
# sessions. Common terms ("Gemini", "Claude", "Review", "Implementation")
# show up in many sessions and produce spurious links across unrelated
# chains; the document-frequency filter excludes them from the linking
# computation. Tuned for ~3500 sessions — phrase cutoff is much tighter
# because the capitalized-phrase extractor is noisier than filename tokens.
DEFAULT_TITLE_DF_CUTOFF   = 0.05    # title keywords must appear in <5% of sessions
DEFAULT_PHRASE_DF_CUTOFF  = 0.015   # content phrases must appear in <1.5% of sessions

# Words to drop from filename keyword extraction. Includes platform prefixes
# and date markers the parsers commonly emit, plus generic words that show
# up across many session titles without telling us anything topical.
_FILENAME_STOP_WORDS = frozenset((
    # Platforms / parser markers
    "claude", "chatgpt", "gemini", "ora", "ai", "gpt", "raw", "chats",
    # Generic conversation-shape words
    "chat", "conversation", "discussion", "exchange", "session", "message",
    "messages", "thread", "threads", "topic", "topics",
    # Generic verbs
    "and", "the", "for", "with", "about", "from", "into", "this", "that",
    "these", "those", "what", "when", "where", "why", "how", "more",
    "less", "new", "old", "good", "bad", "best", "first", "last",
    "another", "more", "review", "update", "draft", "version", "final",
    "part", "vol", "volume", "outline",
    # Stop words from common natural English
    "is", "are", "was", "were", "has", "have", "had", "will", "would",
    "could", "should", "can", "may", "might", "must",
))

# Match four-digit YYYY+MMDD or YYYYMMDD date prefixes in filenames.
_FILENAME_DATE_RE = re.compile(r"\b\d{6,8}\b")
# Punctuation / separator stripping. Treat `_` as a separator too —
# vault and chat-file filenames frequently use it as a word break.
_FILENAME_SEP_RE  = re.compile(r"[^A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Session record
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """One chat session (one source `.md` file)."""
    session_id:        str            # stable hash of source_chat path
    source_chat:       str            # absolute or normalized path
    source_platform:   str
    title_keywords:    set[str]       # method 1 input
    key_phrases:       list[str]      # method 2 input
    fingerprint:       str            # joined key_phrases (method 2 secondary)
    cleaned_pair_paths: list[str]     # all cleaned-pair files for this session
    first_when:        Optional[datetime] = None
    last_when:         Optional[datetime] = None

    @property
    def pair_count(self) -> int:
        return len(self.cleaned_pair_paths)


@dataclass
class Chain:
    """A connected component in the session-similarity graph."""
    chain_id:        str
    chain_label:     str               # human-readable (most-common keyword)
    session_ids:     list[str]
    session_count:   int
    first_when:      Optional[datetime] = None
    last_when:       Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "chain_id":      self.chain_id,
            "chain_label":   self.chain_label,
            "session_ids":   self.session_ids,
            "session_count": self.session_count,
            "first_when":    (self.first_when.isoformat(timespec="seconds")
                              if self.first_when else None),
            "last_when":     (self.last_when.isoformat(timespec="seconds")
                              if self.last_when else None),
        }


# ---------------------------------------------------------------------------
# Session id derivation
# ---------------------------------------------------------------------------


def derive_session_id(source_chat: str) -> str:
    """Stable 12-char hex id derived from the source `.md` path. Re-running
    detection produces the same ids."""
    h = hashlib.sha256()
    h.update((source_chat or "").encode("utf-8"))
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Filename keyword extraction (method 1 input)
# ---------------------------------------------------------------------------


def extract_title_keywords(source_chat: str) -> set[str]:
    """Pull distinctive keywords from a source-chat filename.

    Drops platform prefixes (Claude/ChatGPT/Gemini), date prefixes, file
    extensions, and the small `_FILENAME_STOP_WORDS` set. Keeps tokens
    that are at least 3 chars and not pure digits.

    Example: "Claude 20260417 American Jesus Outline Prep.md"
        → {"american", "jesus", "prep"}
    """
    if not source_chat:
        return set()
    name = Path(source_chat).stem
    # Drop date-like tokens BEFORE general tokenization so 8-digit dates
    # don't survive as keywords.
    name = _FILENAME_DATE_RE.sub(" ", name)
    # Tokenize on any non-word character.
    tokens = _FILENAME_SEP_RE.split(name.lower())
    out: set[str] = set()
    for tok in tokens:
        if len(tok) < 3:
            continue
        if tok.isdigit():
            continue
        if tok in _FILENAME_STOP_WORDS:
            continue
        out.add(tok)
    return out


# ---------------------------------------------------------------------------
# Topic key-phrase extraction (method 2 input)
# ---------------------------------------------------------------------------


def extract_session_key_phrases(
    title: str,
    aggregated_user_text: str,
    aggregated_ai_text: str = "",
    max_n: int = DEFAULT_PHRASES_PER_SESSION,
) -> list[str]:
    """Extract top-N capitalized noun phrases from a session's content.

    Reuses `vault_indexer.extract_key_phrases` (same extractor the
    Phase 0 vault index uses) so chain detection and vault matching
    share a consistent notion of "topic".

    The aggregated text combines user + AI sides because the AI tends
    to repeat user terminology — both sides reinforce the topical
    fingerprint. We cap input length to keep extraction fast across
    thousands of sessions.
    """
    # Cap aggregated body to keep extraction cost linear; the extractor
    # already inspects only the first 800 chars so we don't lose anything
    # by trimming hard here.
    body = (aggregated_user_text[:4000] + "\n"
            + aggregated_ai_text[:2000])
    return extract_key_phrases(title, body, max_n=max_n)


def normalize_phrase(phrase: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation. Used for set
    membership comparison so 'American Jesus' and 'american jesus' match."""
    return re.sub(r"\s+", " ", phrase.lower().strip())


# ---------------------------------------------------------------------------
# Edge detection (pairwise comparison via inverted index)
# ---------------------------------------------------------------------------


def _build_inverted_index_keywords(
    sessions: list[Session],
) -> dict[str, list[int]]:
    """keyword → list of session indices that have it."""
    inv: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(sessions):
        for kw in s.title_keywords:
            inv[kw].append(i)
    return inv


def _build_inverted_index_phrases(
    sessions: list[Session],
) -> dict[str, list[int]]:
    """normalized phrase → list of session indices that have it."""
    inv: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(sessions):
        for p in s.key_phrases:
            inv[normalize_phrase(p)].append(i)
    return inv


def _shared_terms_count(
    a: Iterable[str], b: Iterable[str],
    distinctive: Optional[set[str]] = None,
) -> int:
    """Cardinality of intersection of two iterables (treated as sets).

    If `distinctive` is given, only count terms in that set — terms that
    are too common across the corpus get dropped before counting.
    """
    sa, sb = set(a), set(b)
    common = sa & sb
    if distinctive is not None:
        common &= distinctive
    return len(common)


def _shared_phrases_count(
    a: list[str], b: list[str],
    distinctive: Optional[set[str]] = None,
) -> int:
    """Same as `_shared_terms_count` but normalizes each phrase first."""
    sa = {normalize_phrase(p) for p in a}
    sb = {normalize_phrase(p) for p in b}
    common = sa & sb
    if distinctive is not None:
        common &= distinctive
    return len(common)


# Below this corpus size, every term is treated as distinctive — the DF
# filter only kicks in once we have enough sessions for "common" to mean
# something. A 3-session test corpus has DF 67% on any shared term; we
# don't want to throw those out.
_DF_FILTER_MIN_CORPUS = 20
# Even in a large corpus, a term appearing in this absolute count or
# fewer is still considered distinctive — protects mid-size chains
# (e.g. a 15-session American Jesus chain) from being filtered out.
_DF_FILTER_MIN_DISTINCTIVE_COUNT = 10


def _build_distinctive_set(
    sessions: list[Session],
    field: str,
    df_cutoff: float,
) -> set[str]:
    """Return the set of terms that are "distinctive" — sparse enough
    across the corpus that two sessions sharing them probably mean
    something topical.

    A term is distinctive if its document frequency is at or below
    `max(_DF_FILTER_MIN_DISTINCTIVE_COUNT, int(df_cutoff * n))`. For
    small corpora (`n <= _DF_FILTER_MIN_CORPUS`) the filter is disabled
    — every term is treated as distinctive, since "common" is meaningless
    when there's only a handful of sessions.

    `field` is either "title_keywords" (already lowercase) or
    "key_phrases" (raw — normalized inside).
    """
    n = len(sessions)
    if n == 0:
        return set()
    df: Counter[str] = Counter()
    for s in sessions:
        if field == "title_keywords":
            terms = set(s.title_keywords)
        else:
            terms = {normalize_phrase(p) for p in s.key_phrases}
        for t in terms:
            df[t] += 1
    if n <= _DF_FILTER_MIN_CORPUS:
        return set(df.keys())   # everything distinctive in a small corpus
    cutoff_count = max(
        _DF_FILTER_MIN_DISTINCTIVE_COUNT,
        int(df_cutoff * n),
    )
    return {t for t, c in df.items() if c <= cutoff_count}


def _candidate_pairs_from_inverted(
    sessions: list[Session],
    inv: dict[str, list[int]],
    min_pair_size: int = 2,
) -> set[tuple[int, int]]:
    """Yield candidate (i, j) pairs from an inverted index.

    A pair is a candidate iff at least one term hits both sessions.
    `min_pair_size` is irrelevant here — it's the threshold check that
    decides whether to actually link them.
    """
    candidates: set[tuple[int, int]] = set()
    for term, idxs in inv.items():
        if len(idxs) < 2:
            continue
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                if a > b:
                    a, b = b, a
                candidates.add((a, b))
    return candidates


# ---------------------------------------------------------------------------
# Union-find (for connected components)
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]   # path compression
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ---------------------------------------------------------------------------
# Chain assembly
# ---------------------------------------------------------------------------


def _chain_label_for(sessions: list[Session]) -> str:
    """Most-common shared term across a chain — used as the human-readable
    label. Picks from the union of title keywords + normalized key phrases."""
    counter: Counter[str] = Counter()
    for s in sessions:
        counter.update(s.title_keywords)
        for p in s.key_phrases:
            counter[normalize_phrase(p)] += 1
    if not counter:
        return "(unlabeled)"
    # Filter labels: pick the term that appears in the highest fraction
    # of sessions to avoid letting one verbose session dominate.
    n = len(sessions)
    scored: list[tuple[float, str]] = []
    for term, cnt in counter.items():
        # Count sessions in which the term appears (presence, not freq).
        present = sum(
            1 for s in sessions
            if term in s.title_keywords
            or term in {normalize_phrase(p) for p in s.key_phrases}
        )
        if present < 2 and n > 1:
            continue   # term appears in fewer than 2 sessions of a chain
        scored.append((present / n, term))
    if not scored:
        scored = [(c / max(1, n), t) for t, c in counter.most_common(5)]
    scored.sort(reverse=True)
    return scored[0][1]


def _stable_chain_id(session_ids: list[str]) -> str:
    """SHA-256 of sorted session ids — stable across re-runs given the
    same set of sessions in the chain."""
    h = hashlib.sha256()
    for sid in sorted(session_ids):
        h.update(sid.encode("utf-8"))
        h.update(b"|")
    return "chain-" + h.hexdigest()[:10]


def detect_chains(
    sessions: list[Session],
    *,
    min_shared_title_keywords: int = DEFAULT_MIN_SHARED_TITLE_KEYWORDS,
    min_shared_phrases:        int = DEFAULT_MIN_SHARED_PHRASES,
    title_df_cutoff:           float = DEFAULT_TITLE_DF_CUTOFF,
    phrase_df_cutoff:          float = DEFAULT_PHRASE_DF_CUTOFF,
) -> list[Chain]:
    """Run methods 1 + 2 over the session list, return one Chain per
    connected component.

    Document-frequency cutoffs filter out terms that appear in too many
    sessions (e.g. "Gemini", "Claude Code") — these would otherwise
    create spurious links and over-cluster unrelated work.

    Single-session chains (orphans with no edges) are still returned —
    every session ends up in some chain, even if it's a chain of one.
    """
    n = len(sessions)
    if n == 0:
        return []

    uf = _UnionFind(n)

    # Build distinctive-term sets for both methods. A term is distinctive
    # if it appears in fewer than the cutoff fraction of all sessions.
    distinctive_titles  = _build_distinctive_set(sessions, "title_keywords",
                                                  title_df_cutoff)
    distinctive_phrases = _build_distinctive_set(sessions, "key_phrases",
                                                  phrase_df_cutoff)

    # --- Method 1: title-keyword overlap via inverted index ---------------
    title_inv = _build_inverted_index_keywords(sessions)
    title_candidates = _candidate_pairs_from_inverted(sessions, title_inv)
    for i, j in title_candidates:
        if _shared_terms_count(
            sessions[i].title_keywords, sessions[j].title_keywords,
            distinctive=distinctive_titles,
        ) >= min_shared_title_keywords:
            uf.union(i, j)

    # --- Method 2: topic-fingerprint overlap via inverted index -----------
    phrase_inv = _build_inverted_index_phrases(sessions)
    phrase_candidates = _candidate_pairs_from_inverted(sessions, phrase_inv)
    for i, j in phrase_candidates:
        if uf.find(i) == uf.find(j):
            continue   # already linked by method 1
        if _shared_phrases_count(
            sessions[i].key_phrases, sessions[j].key_phrases,
            distinctive=distinctive_phrases,
        ) >= min_shared_phrases:
            uf.union(i, j)

    # Group sessions by root -> one chain per root.
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    chains: list[Chain] = []
    for root, idxs in groups.items():
        members = [sessions[i] for i in idxs]
        sids = [s.session_id for s in members]
        # First/last when across the chain.
        timestamps = [s.first_when for s in members if s.first_when]
        lasts      = [s.last_when  for s in members if s.last_when]
        chain = Chain(
            chain_id     = _stable_chain_id(sids),
            chain_label  = _chain_label_for(members),
            session_ids  = sorted(sids),
            session_count= len(sids),
            first_when   = min(timestamps) if timestamps else None,
            last_when    = max(lasts)      if lasts      else None,
        )
        chains.append(chain)

    # Sort chains by size desc, then label, for stable output.
    chains.sort(key=lambda c: (-c.session_count, c.chain_label))
    return chains


# ---------------------------------------------------------------------------
# Chain index file (persistence)
# ---------------------------------------------------------------------------


def save_chain_index(
    chains: list[Chain],
    sessions: list[Session],
    path: str = CHAIN_INDEX_DEFAULT,
) -> None:
    """Persist the chain index to JSON. Includes per-session lookup table
    so downstream consumers can map session_id → chain_id without parsing
    the chains list."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    session_to_chain: dict[str, str] = {}
    for c in chains:
        for sid in c.session_ids:
            session_to_chain[sid] = c.chain_id
    payload = {
        "version":          1,
        "built_at":         datetime.now().isoformat(timespec="seconds"),
        "session_count":    len(sessions),
        "chain_count":      len(chains),
        "chains":           [c.to_dict() for c in chains],
        "session_to_chain": session_to_chain,
        # Per-session metadata — useful for inspection without re-reading
        # cleaned-pair files.
        "sessions": {
            s.session_id: {
                "source_chat":      s.source_chat,
                "source_platform":  s.source_platform,
                "title_keywords":   sorted(s.title_keywords),
                "key_phrases":      s.key_phrases,
                "pair_count":       s.pair_count,
                "first_when":       (s.first_when.isoformat(timespec="seconds")
                                     if s.first_when else None),
                "last_when":        (s.last_when.isoformat(timespec="seconds")
                                     if s.last_when else None),
            }
            for s in sessions
        },
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(p)


def load_chain_index(path: str = CHAIN_INDEX_DEFAULT) -> dict:
    """Load the persisted chain index. Returns an empty index if the file
    doesn't exist."""
    p = Path(path).expanduser()
    if not p.exists():
        return {
            "version":          1,
            "session_count":    0,
            "chain_count":      0,
            "chains":           [],
            "session_to_chain": {},
            "sessions":         {},
        }
    return json.loads(p.read_text(encoding="utf-8"))


__all__ = [
    "CHAIN_INDEX_DEFAULT",
    "DEFAULT_MIN_SHARED_TITLE_KEYWORDS",
    "DEFAULT_MIN_SHARED_PHRASES",
    "Session",
    "Chain",
    "derive_session_id",
    "extract_title_keywords",
    "extract_session_key_phrases",
    "normalize_phrase",
    "detect_chains",
    "save_chain_index",
    "load_chain_index",
]
