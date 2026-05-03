"""Context header + thread continuity for cleaned-pair files (Phase 1.9).

Each cleaned-pair file gets a multi-level context block at the top:

    ## Context
    ### Session context
    <one paragraph about the source chat as a whole>
    ### Pair context
    <one paragraph about where this pair sits in the chat>

Plus a `thread_id` recorded in YAML frontmatter that lets downstream
phases group consecutive same-topic pairs.

This module provides:

  * `ThreadTracker` — assigns sequential thread ids within a chat,
    advancing the counter when topic keywords shift between pairs.
  * `build_session_context(raw_chat)` — one paragraph derived from
    chat metadata.
  * `build_pair_context(raw_chat, pair_index, cleaned_pair, prior, thread_id)`
    — one paragraph naming this pair's position + topic + thread state.
  * `build_filename(when, cleaned_pair)` — the cleaned-pair filename
    (`YYYY-MM-DD_HH-MM_keyword-keyword-keyword.md`) for cross-linking.

Thread continuity is heuristic — keyword-set overlap between
consecutive pairs. Acceptable for the cleanup pass; downstream
extraction can refine.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from orchestrator.historical import Platform, RawChat
from orchestrator.historical.pair_cleanup import CleanedPair


# ---------------------------------------------------------------------------
# Keyword extraction (lightweight)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    "the a an of in on at to for with by from as is are was were be been "
    "being have has had do does did will would shall should may might can "
    "could and but or if while because until although since this that these "
    "those it its they them their he his she her you your we our i me my "
    "what which who whom whose how why when where there here also even just "
    "only own same some any all each every both few more most other such no "
    "nor not very still already well make use used using how very".split()
)

_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b")


def extract_keywords(text: str, max_n: int = 8) -> list[str]:
    """Return up to `max_n` lowercase keywords from `text`. Cheap heuristic."""
    if not text:
        return []
    words = _WORD_RE.findall(text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in _STOP_WORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_n:
            break
    return out


def keyword_set(cleaned_pair: CleanedPair, max_n: int = 8) -> set[str]:
    """Combined keyword set from cleaned user input + cleaned AI response."""
    combined = (cleaned_pair.cleaned_user_input or "") + " " + \
               (cleaned_pair.cleaned_ai_response or "")
    return set(extract_keywords(combined, max_n=max_n))


# ---------------------------------------------------------------------------
# Thread tracker
# ---------------------------------------------------------------------------


THREAD_OVERLAP_THRESHOLD = 0.3   # ≥30% keyword overlap → same thread


class ThreadTracker:
    """Assigns thread ids to pairs based on topic-keyword overlap.

    State machine:
      - First pair starts thread #1.
      - Each subsequent pair shares the prior thread id IF its keyword
        set has ≥THREAD_OVERLAP_THRESHOLD with the prior pair's set.
      - Otherwise a new thread starts (counter increments).

    Thread id format: `thread_<8-hex-of-conversation-id>_<NNN>`.
    """

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id or "unknown"
        self._hash = hashlib.sha256(self.conversation_id.encode("utf-8")).hexdigest()[:8]
        self._thread_counter = 0
        self._last_keywords: set[str] = set()

    def assign(self, current_keywords: set[str]) -> str:
        """Return the thread id for the current pair."""
        if not self._last_keywords:
            self._thread_counter = 1
            self._last_keywords = set(current_keywords)
            return self._format_id()
        denom = max(len(self._last_keywords), 1)
        overlap = len(current_keywords & self._last_keywords) / denom
        if overlap < THREAD_OVERLAP_THRESHOLD:
            self._thread_counter += 1
        self._last_keywords = set(current_keywords)
        return self._format_id()

    def _format_id(self) -> str:
        return f"thread_{self._hash}_{self._thread_counter:03d}"


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

_FILENAME_PUNCT_RE = re.compile(r"[^\w\s]+")


def _filename_slug(text: str, max_words: int = 4) -> str:
    """Produce a hyphenated keyword slug for a filename."""
    if not text:
        return "conversation"
    norm = _FILENAME_PUNCT_RE.sub(" ", text.lower())
    words = [w for w in norm.split() if len(w) > 2 and w not in _STOP_WORDS]
    if not words:
        return "conversation"
    return "-".join(words[:max_words])


def build_filename(when: datetime, cleaned_pair: CleanedPair) -> str:
    """Filename for a cleaned-pair file: YYYY-MM-DD_HH-MM_slug.md.

    Slug derives from the cleaned user input (first ~500 chars),
    fallback to AI response, fallback to 'conversation'.
    """
    date_str = when.strftime("%Y-%m-%d")
    time_str = when.strftime("%H-%M")
    source_text = (cleaned_pair.cleaned_user_input
                    or cleaned_pair.cleaned_ai_response
                    or "conversation")[:500]
    slug = _filename_slug(source_text)
    return f"{date_str}_{time_str}_{slug}.md"


# ---------------------------------------------------------------------------
# Context paragraph builders
# ---------------------------------------------------------------------------


def build_session_context(chat: RawChat) -> str:
    """One paragraph describing the source chat as a whole."""
    title = (chat.metadata.title or "Untitled chat").strip()
    platform = chat.metadata.platform.value if chat.metadata.platform else "unknown"
    created = chat.metadata.created_at
    date_str = created.strftime("%Y-%m-%d") if created else "unknown date"
    pairs = chat.to_pairs()
    n_pairs = len(pairs)

    # Derive a session topic from the FIRST pair's keywords (proxy for
    # what the chat opened on).
    session_topic = ""
    if pairs:
        first_user = pairs[0].user_content or ""
        first_kw = extract_keywords(first_user, max_n=4)
        if first_kw:
            session_topic = ", ".join(first_kw)

    parts = [
        f"Conversation '{title}' on {platform}, dated {date_str}, "
        f"comprising {n_pairs} prompt+response pair(s).",
    ]
    if session_topic:
        parts.append(f"Opening topic keywords: {session_topic}.")
    return " ".join(parts)


def build_pair_context(
    chat:               RawChat,
    pair_index:         int,
    cleaned_pair:       CleanedPair,
    prior_cleaned_pair: Optional[CleanedPair] = None,
    thread_id:          str = "",
    is_thread_start:    bool = False,
) -> str:
    """One paragraph describing this pair's position + thread state."""
    pairs = chat.to_pairs()
    total = len(pairs)
    parts: list[str] = []
    parts.append(f"Pair {cleaned_pair.pair_num} of {total}.")

    pair_kw = extract_keywords(cleaned_pair.cleaned_user_input or "", max_n=5)
    if pair_kw:
        parts.append(f"Topic keywords for this pair: {', '.join(pair_kw)}.")

    if is_thread_start and pair_index > 0 and prior_cleaned_pair:
        prior_kw = extract_keywords(
            prior_cleaned_pair.cleaned_user_input or "", max_n=4,
        )
        if prior_kw:
            parts.append(
                f"This pair begins a new thread, departing from prior topic "
                f"({', '.join(prior_kw)})."
            )
        else:
            parts.append("This pair begins a new thread.")
    elif prior_cleaned_pair and thread_id:
        parts.append(f"Continues thread {thread_id}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Combined context-header record
# ---------------------------------------------------------------------------


@dataclass
class ContextHeader:
    """Computed header info attached to one cleaned-pair file."""
    session_context:    str = ""
    pair_context:       str = ""
    thread_id:          str = ""
    is_thread_start:    bool = False
    prior_pair_file:    str = ""
    next_pair_file:     str = ""
    pair_filename:      str = ""
    pair_keywords:      list[str] = field(default_factory=list)


def build_context_header(
    chat:               RawChat,
    pair_index:         int,
    cleaned_pairs:      list[CleanedPair],
    thread_tracker:     ThreadTracker,
) -> ContextHeader:
    """Compute the full context header for `cleaned_pairs[pair_index]`.

    `cleaned_pairs` is the ordered list of CleanedPair records for the
    whole chat (so we can look up prior/next filenames). The thread
    tracker should be reset for each chat and called in pair order.
    """
    cleaned_pair = cleaned_pairs[pair_index]
    when = cleaned_pair.when or datetime.now()

    # Topic + thread
    pair_kw = keyword_set(cleaned_pair)
    prior_thread_id = thread_tracker._format_id() if thread_tracker._last_keywords else ""
    thread_id = thread_tracker.assign(pair_kw)
    is_new_thread = (prior_thread_id != "" and thread_id != prior_thread_id)

    # Filenames
    filename = build_filename(when, cleaned_pair)
    prior_file = ""
    if pair_index > 0:
        prior = cleaned_pairs[pair_index - 1]
        prior_when = prior.when or datetime.now()
        prior_file = build_filename(prior_when, prior)
    next_file = ""
    if pair_index < len(cleaned_pairs) - 1:
        nxt = cleaned_pairs[pair_index + 1]
        nxt_when = nxt.when or datetime.now()
        next_file = build_filename(nxt_when, nxt)

    # Paragraphs
    session_ctx = build_session_context(chat)
    prior_cleaned = cleaned_pairs[pair_index - 1] if pair_index > 0 else None
    pair_ctx = build_pair_context(
        chat, pair_index, cleaned_pair,
        prior_cleaned_pair=prior_cleaned,
        thread_id=thread_id,
        is_thread_start=is_new_thread,
    )

    return ContextHeader(
        session_context=session_ctx,
        pair_context=pair_ctx,
        thread_id=thread_id,
        is_thread_start=is_new_thread,
        prior_pair_file=prior_file,
        next_pair_file=next_file,
        pair_filename=filename,
        pair_keywords=sorted(pair_kw),
    )


__all__ = [
    "THREAD_OVERLAP_THRESHOLD",
    "ContextHeader",
    "ThreadTracker",
    "extract_keywords",
    "keyword_set",
    "build_filename",
    "build_session_context",
    "build_pair_context",
    "build_context_header",
]
