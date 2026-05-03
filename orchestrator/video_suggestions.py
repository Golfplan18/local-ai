"""Video Editing Suggestions framework — runtime implementation.

Two paths:

1. ``generate_suggestions_heuristic(transcript, ...)`` — pure-Python
   deterministic suggestion generator. Walks the transcript looking
   for filler words, silence gaps, and topic shifts. Used as the
   default and for tests; no model call required.

2. ``generate_suggestions_llm(transcript, model_callable, ...)`` —
   feeds the transcript into a model with the framework prompt and
   parses the JSON response. The model_callable is injected so tests
   and live runs can both go through the same path. (Live wiring —
   the actual call into the local mlx_lm.server — is left for the
   user's gating once API keys are settled per the project's broader
   live-fire policy.)

Both paths emit JSON validated against
``~/ora/config/framework-schemas/video-editing-suggestions.schema.json``.
Validation failures raise ``SuggestionValidationError``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

# ── schema validation ────────────────────────────────────────────────────────

_SCHEMA_PATH = Path.home() / "ora" / "config" / "framework-schemas" / \
               "video-editing-suggestions.schema.json"

_SCHEMA_CACHE: dict | None = None


class SuggestionValidationError(Exception):
    pass


def _load_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def validate_suggestions(payload: dict) -> None:
    """Raise SuggestionValidationError if payload doesn't match schema.

    Uses jsonschema if available; otherwise applies hand-rolled checks
    sufficient for the four suggestion types (kept in sync with the
    JSON Schema file). Runtime invariants that the JSON schema can't
    express (end_ms > start_ms, etc.) run regardless of which path
    above was taken.
    """
    try:
        import jsonschema  # type: ignore
        try:
            jsonschema.validate(instance=payload, schema=_load_schema())
        except jsonschema.ValidationError as e:  # type: ignore
            raise SuggestionValidationError(str(e)) from e
    except ImportError:
        _validate_minimal(payload)

    # Runtime invariants the JSON schema can't express.
    for i, sug in enumerate(payload.get("suggestions") or []):
        if sug.get("type") == "cut":
            start = sug.get("start_ms")
            end = sug.get("end_ms")
            if start is None or end is None or end <= start:
                raise SuggestionValidationError(
                    f"cut[{i}] end_ms must be strictly greater than start_ms "
                    f"(got start={start}, end={end})"
                )


def _validate_minimal(payload: dict) -> None:
    """Schema-shape sanity checks that don't require jsonschema."""
    if not isinstance(payload, dict):
        raise SuggestionValidationError("payload must be a JSON object")
    if not payload.get("entry_id") or not isinstance(payload["entry_id"], str):
        raise SuggestionValidationError("entry_id is required and must be a string")
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        raise SuggestionValidationError("suggestions must be an array")
    for i, sug in enumerate(suggestions):
        if not isinstance(sug, dict):
            raise SuggestionValidationError(f"suggestion[{i}] must be an object")
        t = sug.get("type")
        if t == "cut":
            for k in ("start_ms", "end_ms", "reason"):
                if k not in sug:
                    raise SuggestionValidationError(f"cut[{i}] missing {k}")
            if sug["end_ms"] <= sug["start_ms"]:
                raise SuggestionValidationError(f"cut[{i}] end_ms must exceed start_ms")
        elif t == "chapter":
            for k in ("at_ms", "label", "reason"):
                if k not in sug:
                    raise SuggestionValidationError(f"chapter[{i}] missing {k}")
        elif t == "title_card":
            for k in ("at_ms", "duration_ms", "title", "reason"):
                if k not in sug:
                    raise SuggestionValidationError(f"title_card[{i}] missing {k}")
        elif t == "transition":
            for k in ("at_ms", "duration_ms", "kind", "reason"):
                if k not in sug:
                    raise SuggestionValidationError(f"transition[{i}] missing {k}")
            if sug["kind"] not in ("fade", "dissolve", "cut"):
                raise SuggestionValidationError(f"transition[{i}] invalid kind")
        else:
            raise SuggestionValidationError(f"suggestion[{i}] unknown type: {t!r}")


# ── heuristic generator ──────────────────────────────────────────────────────

# Single-word filler (segment text is *just* one of these — strict).
_FILLER_WORDS = {
    "um", "umm", "uh", "uhh", "er", "erm", "hmm", "mhm",
}

# Discourse markers that often start a new section.
_CHAPTER_DISCOURSE_MARKERS = {
    "so", "okay", "ok", "alright", "right",
    "now", "next", "moving on", "let's", "so let's",
}

# Words that signal an intro is already in place.
_INTRO_OPENERS = {
    "welcome", "hello", "hi everyone", "hi everybody",
    "today", "in this", "let's talk about",
}

_FALSE_START_LOOKBACK = 4  # words


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s']", "", text.lower()).strip()


def _segment_words(text: str) -> list[str]:
    return _normalize(text).split()


def _is_filler_only(text: str) -> bool:
    words = _segment_words(text)
    if not words:
        return False
    # Single-word filler segment, OR multi-word but all filler.
    return all(w in _FILLER_WORDS for w in words)


def _starts_with_discourse_marker(text: str) -> bool:
    norm = _normalize(text)
    for marker in _CHAPTER_DISCOURSE_MARKERS:
        if norm.startswith(marker + " ") or norm == marker:
            return True
    return False


def _looks_like_intro(text: str) -> bool:
    norm = _normalize(text)
    return any(norm.startswith(opener) for opener in _INTRO_OPENERS)


def _first_n_words(text: str, n: int) -> tuple[str, ...]:
    return tuple(_segment_words(text)[:n])


def generate_suggestions_heuristic(
    transcript: dict,
    entry_id: str,
    goals: str | None = None,
    existing_clips: list[dict] | None = None,
) -> dict:
    """Produce suggestions from the transcript without any model call.

    Deterministic — same transcript yields same suggestions. Used as
    the default generator; the LLM path layers on top when wired.
    """
    segments = transcript.get("segments") or []
    duration_ms = int(transcript.get("duration_ms") or 0)
    suggestions: list[dict] = []

    if not segments:
        return _emit({
            "entry_id": entry_id,
            "summary": "Transcript is empty; no suggestions generated.",
            "suggestions": [],
        })

    # ── filler-only-segment cuts ─────────────────────────────────────────
    # Budget: at least 6 cuts always allowed (small clips), scaling
    # upward at ~12 cuts per 10 minutes for longer content.
    cut_count = 0
    cut_budget = max(6, int(duration_ms / 50_000))
    for seg in segments:
        if cut_count >= cut_budget:
            break
        text = (seg.get("text") or "").strip()
        if _is_filler_only(text):
            start = int(seg.get("start_ms") or 0)
            end = int(seg.get("end_ms") or 0)
            if end - start < 200:
                continue
            suggestions.append({
                "type": "cut",
                "start_ms": start,
                "end_ms": end,
                "reason": f"Filler-only segment (\"{text}\").",
                "category": "filler",
            })
            cut_count += 1

    # ── silence-gap cuts ─────────────────────────────────────────────────
    for i in range(1, len(segments)):
        if cut_count >= cut_budget:
            break
        prev_end = int(segments[i - 1].get("end_ms") or 0)
        cur_start = int(segments[i].get("start_ms") or 0)
        gap = cur_start - prev_end
        if gap >= 1500:
            suggestions.append({
                "type": "cut",
                "start_ms": prev_end,
                "end_ms": cur_start,
                "reason": f"Silence gap of {gap // 1000}.{(gap // 100) % 10}s.",
                "category": "silence",
            })
            cut_count += 1

    # ── false-start detection ────────────────────────────────────────────
    for i in range(1, len(segments)):
        if cut_count >= cut_budget:
            break
        prev_words = _first_n_words(
            segments[i - 1].get("text") or "", _FALSE_START_LOOKBACK
        )
        cur_words = _first_n_words(
            segments[i].get("text") or "", _FALSE_START_LOOKBACK
        )
        if (
            len(prev_words) == _FALSE_START_LOOKBACK
            and prev_words == cur_words
        ):
            start = int(segments[i - 1].get("start_ms") or 0)
            end = int(segments[i - 1].get("end_ms") or 0)
            if end - start >= 200:
                suggestions.append({
                    "type": "cut",
                    "start_ms": start,
                    "end_ms": end,
                    "reason": "Likely false start — same opening repeats in the next segment.",
                    "category": "false_start",
                })
                cut_count += 1

    # ── chapter markers ─────────────────────────────────────────────────
    chapter_count = 0
    chapter_budget = max(2, int(duration_ms / 120_000))
    for i in range(1, len(segments)):
        if chapter_count >= chapter_budget:
            break
        prev_end = int(segments[i - 1].get("end_ms") or 0)
        cur_start = int(segments[i].get("start_ms") or 0)
        gap = cur_start - prev_end
        if gap < 1000:
            continue
        text = (segments[i].get("text") or "").strip()
        if not _starts_with_discourse_marker(text):
            continue
        # Use the first phrase as the label (truncate at 60).
        words = text.split()
        label = " ".join(words[:8])
        if len(label) > 60:
            label = label[:57].rstrip() + "..."
        if not label:
            continue
        suggestions.append({
            "type": "chapter",
            "at_ms": cur_start,
            "label": label,
            "reason": (
                f"Pause of {gap // 1000}s followed by a topic-shift cue "
                f"(\"{words[0]}\")."
            ),
        })
        chapter_count += 1

    # ── title card if no clear intro ─────────────────────────────────────
    first_text = (segments[0].get("text") or "").strip()
    if not _looks_like_intro(first_text) and duration_ms >= 5000:
        # Heuristic title: collect the most-said content words from the
        # first 60 seconds.
        early_text = " ".join(
            (s.get("text") or "")
            for s in segments
            if int(s.get("start_ms") or 0) < 60_000
        )
        topic = _guess_topic(early_text)
        if topic:
            suggestions.append({
                "type": "title_card",
                "at_ms": 0,
                "duration_ms": 3000,
                "title": topic,
                "reason": "Clip lacks a clear opening; a title card frames the topic for viewers.",
            })

    # ── order by source-time ─────────────────────────────────────────────
    def _key(s):
        return s.get("start_ms") if "start_ms" in s else s.get("at_ms", 0)
    suggestions.sort(key=_key)

    summary = _build_summary(suggestions, duration_ms)
    return _emit({
        "entry_id": entry_id,
        "summary": summary,
        "suggestions": suggestions,
    })


def _guess_topic(text: str) -> str | None:
    """Pick the longest non-stopword bigram/word from the first minute."""
    norm = _normalize(text)
    if not norm:
        return None
    stopwords = {
        "the", "a", "an", "is", "and", "or", "but", "this", "that", "these", "those",
        "i", "you", "we", "they", "he", "she", "it", "of", "to", "in", "on", "at",
        "for", "with", "by", "from", "up", "down", "as", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "shall", "can", "if", "then",
        "so", "now", "okay", "ok", "well", "really", "just", "like", "going", "got",
    }
    words = [w for w in norm.split() if w not in stopwords and len(w) > 2]
    if not words:
        return None
    # Count word frequency, pick the top.
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    if not top:
        return None
    candidate = " ".join(w.capitalize() for w, _ in top[:2])
    if len(candidate) > 50:
        candidate = candidate[:47].rstrip() + "..."
    return candidate or None


def _build_summary(suggestions: list[dict], duration_ms: int) -> str:
    if not suggestions:
        return "No edits suggested for this clip."
    by_type: dict[str, int] = {}
    saved_ms = 0
    for s in suggestions:
        by_type[s["type"]] = by_type.get(s["type"], 0) + 1
        if s["type"] == "cut":
            saved_ms += int(s["end_ms"]) - int(s["start_ms"])
    parts = []
    if by_type.get("cut"):
        secs_saved = saved_ms / 1000.0
        parts.append(
            f"{by_type['cut']} cut(s) totaling {secs_saved:.1f}s "
            f"(of {duration_ms / 1000.0:.0f}s total)"
        )
    if by_type.get("chapter"):
        parts.append(f"{by_type['chapter']} chapter marker(s)")
    if by_type.get("title_card"):
        parts.append(f"{by_type['title_card']} title card")
    if by_type.get("transition"):
        parts.append(f"{by_type['transition']} transition(s)")
    return "Suggested: " + ", ".join(parts) + "."


def _emit(payload: dict) -> dict:
    """Validate before returning."""
    validate_suggestions(payload)
    return payload


# ── LLM path (wired but stubbed for live use) ────────────────────────────────

def generate_suggestions_llm(
    transcript: dict,
    entry_id: str,
    model_callable: Callable[[str], str],
    goals: str | None = None,
    existing_clips: list[dict] | None = None,
) -> dict:
    """Run the framework via a model.

    ``model_callable`` takes a system+user prompt string and returns the
    raw model response. The caller is responsible for selecting the
    actual model (local mlx_lm.server, Anthropic API, etc.). This
    function only handles prompt assembly + JSON extraction +
    validation.

    Falls back to the heuristic generator on parse failure (with a
    note in the summary).
    """
    prompt = _build_prompt(transcript, entry_id, goals=goals,
                           existing_clips=existing_clips)
    try:
        raw = model_callable(prompt) or ""
    except Exception as e:
        return _fallback(transcript, entry_id, f"model call failed: {e}")

    payload = _extract_json(raw)
    if payload is None:
        return _fallback(transcript, entry_id,
                         "model returned non-JSON; using heuristic suggestions instead.")
    try:
        validate_suggestions(payload)
    except SuggestionValidationError as e:
        return _fallback(transcript, entry_id, f"schema validation: {e}")
    return payload


def _build_prompt(
    transcript: dict,
    entry_id: str,
    goals: str | None = None,
    existing_clips: list[dict] | None = None,
) -> str:
    framework_path = Path.home() / "ora" / "frameworks" / "book" / \
                     "video-editing-suggestions.md"
    framework_text = framework_path.read_text(encoding="utf-8")
    transcript_view = json.dumps({
        "language": transcript.get("language"),
        "duration_ms": transcript.get("duration_ms"),
        "segments": transcript.get("segments") or [],
    }, indent=2)
    parts = [
        "You are running the Video Editing Suggestions framework.",
        "Follow the framework specification exactly. Emit ONLY JSON, no preamble.",
        "",
        framework_text,
        "",
        f"entry_id: {entry_id}",
    ]
    if goals:
        parts.append(f"goals: {goals}")
    if existing_clips:
        parts.append(f"existing_clips: {json.dumps(existing_clips)}")
    parts.append("")
    parts.append("transcript:")
    parts.append(transcript_view)
    parts.append("")
    parts.append("Now emit the suggestions JSON.")
    return "\n".join(parts)


def _extract_json(raw: str) -> dict | None:
    """Pull the first JSON object out of a model response."""
    # Strip markdown code fences if present.
    raw = raw.strip()
    if raw.startswith("```"):
        # Remove leading ```json or ``` and trailing ```
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()
    # Try strict parse first.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: find the first balanced { ... }.
    depth = 0
    start = -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                blob = raw[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _fallback(transcript: dict, entry_id: str, note: str) -> dict:
    payload = generate_suggestions_heuristic(transcript, entry_id)
    if payload.get("summary"):
        payload["summary"] = note + " " + payload["summary"]
    else:
        payload["summary"] = note
    return payload


__all__ = [
    "generate_suggestions_heuristic",
    "generate_suggestions_llm",
    "validate_suggestions",
    "SuggestionValidationError",
]
