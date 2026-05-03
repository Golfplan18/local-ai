"""Paste detection + 4-bucket classification (Phase 1.3).

Given a raw user-input string from a parsed RawPair, this module:

  1. Segments the text into 'personal' (user typed) vs 'pasted'
     (clipboard content) blocks using structural heuristics.
  2. For each pasted segment, runs vault-index lookup first
     (paragraph-hash overlap → 'earlier-draft / mention-only'),
     then applies a 4-bucket classifier (news / opinion / resource
     / other).

The output is an ordered list of Segment records the cleanup
pipeline (Phase 1.7+) and the downstream extraction passes
(Phase 3 news+opinion, Phase 4 resource) consume.

Design choices:
  - Strong paste signals (markdown headings, code blocks, citation
    patterns, length thresholds) flip a block to 'pasted'. Otherwise
    'personal' is the default.
  - Adjacent same-kind blocks are merged into a single Segment so
    a multi-paragraph paste becomes one segment, not five.
  - Classification is heuristic-only here; no model calls. Confidence
    scores are exposed so the cleanup orchestrator can route
    low-confidence segments to a model when needed (Phase 1.7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Segment data structure
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A contiguous block of user-input classified as personal or pasted."""
    kind:            str               # 'personal' | 'pasted'
    content:         str               # the actual text (raw, preserved)
    block_indices:   tuple[int, int]   # (first, last) source-block indices
    classification:  str = ""          # for pasted: 'news'|'opinion'|'resource'|'earlier-draft'|'other'
    confidence:      float = 0.0       # 0.0–1.0 classification confidence
    vault_match:     Optional[dict] = None     # vault entry dict if mature-version match
    heuristic_flags: list[str] = field(default_factory=list)  # signals fired


# ---------------------------------------------------------------------------
# Paste-detection signals (per-block)
# ---------------------------------------------------------------------------


# Markdown structural markers — strong paste signal.
_MD_HEADING_RE          = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_CODE_FENCE_RE          = re.compile(r"^\s*```", re.MULTILINE)
_BLOCKQUOTE_RE          = re.compile(r"^\s{0,3}>\s+\S", re.MULTILINE)
_BULLET_LIST_RE         = re.compile(r"^\s{0,3}[-*+]\s+\S", re.MULTILINE)
_NUMBERED_LIST_RE       = re.compile(r"^\s{0,3}\d+\.\s+\S", re.MULTILINE)

# Citation patterns — strong resource signal.
# Two common forms: `(Smith, 2024)` and `Smith (2024)` and `Smith et al. (2023)`.
_CITATION_PARENS_RE     = re.compile(
    r"(?:\(\s*[A-Z][a-z]+(?:\s+(?:and|et\s+al\.?|&)\s+\w+)?\s*,?\s*\d{4}[a-z]?\s*\))"
    r"|(?:[A-Z][a-z]+(?:\s+et\s+al\.?)?\s+\(\s*\d{4}[a-z]?\s*\))"
)
_CITATION_BRACKETS_RE   = re.compile(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]")
_DOI_RE                 = re.compile(r"\bdoi:\s*\S+", re.IGNORECASE)
_ET_AL_RE               = re.compile(r"\bet\s+al\.?", re.IGNORECASE)

# News-specific signals.
_BYLINE_RE              = re.compile(r"\bBy\s+[A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){1,3}\b")
_DATELINE_RE            = re.compile(r"^[A-Z]{2,}(?:\s+[A-Z]{2,})*\s*[—–-]\s+", re.MULTILINE)
_ATTRIBUTED_QUOTE_RE    = re.compile(r"[\"“][^\"”]{20,}?[\"”]\s*[,.]?\s*(?:said|told|added|noted|stated)")

# Opinion-specific signals.
_OPINION_FRAME_RE       = re.compile(
    r"\b(?:I\s+(?:think|believe|argue|contend|maintain|claim|propose|suggest)|"
    r"in\s+my\s+(?:view|opinion|estimation)|"
    r"the\s+case\s+(?:for|against)|"
    r"why\s+\w+\s+is\s+(?:wrong|right|broken|essential|misguided)|"
    r"the\s+(?:problem|trouble|issue)\s+with)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_RE        = re.compile(r"\b(?:I|my|me|we|our|us)\b")

# Resource-specific section headings.
_RESEARCH_SECTIONS_RE   = re.compile(
    r"^\s{0,3}#{1,6}\s+(?:Abstract|Introduction|Methodology|Methods|"
    r"Results?|Discussion|Conclusions?|References|Bibliography|"
    r"Acknowledgements|Appendix)\b",
    re.MULTILINE | re.IGNORECASE,
)

# Length thresholds.
_PERSONAL_MAX_CHARS     = 300        # below this, default to personal
_LONG_PASTE_THRESHOLD   = 1000       # above this with no first-person, likely pasted
_RESOURCE_MIN_CHARS     = 1000       # rough lower bound for resource classification


# ---------------------------------------------------------------------------
# News-piece signals (improved 2026-05-02): headline + webpage-garbage combo
# ---------------------------------------------------------------------------

# Headline pattern at segment start. A headline is a short title-cased line
# (or ALL-CAPS line) that opens the segment, with no terminal punctuation
# beyond an optional colon and no first-person words. We look at the first
# non-blank line of the segment.
_HEADLINE_TITLE_CASE_RE = re.compile(
    r"^[A-Z][A-Za-z0-9\-:'’,&]*"           # First word cap
    r"(?:\s+(?:[A-Z][A-Za-z0-9\-:'’,&]*"   # title-case continuation
    r"|of|and|the|in|to|for|from|on|with|a|an|or|by|at|as|vs\.?|over|after|"
    r"under|amid|between|against|behind|before|toward|than|how|why))*"
    r"\s*[\?:!]?$"
)

_HEADLINE_ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9\s\-:'’,&\.]{8,120}$")

# Webpage-garbage tokens. Presence of these phrases strongly suggests
# the pasted text came from a webpage scrape (article body + boilerplate),
# not the user's own writing. Each match is one weak signal; multiple
# matches within a segment is a strong news/opinion-piece indicator.
#
# IMPORTANT: news-outlet names (Reuters, NYT, Fox News, etc.) are NOT
# in this list because they appear in legitimate narrative writing too
# (e.g. fiction characters watching Fox News, articles citing Reuters).
# Only structural webpage chrome — login/share/copyright/related-content
# affordances — counts as garbage.
_WEBPAGE_GARBAGE_PATTERNS = [
    r"\bsubscribe\s+(?:to|now|today|for)\b",
    r"\bsign\s+(?:in|up|up\s+for)\b",
    r"\blog\s+in\b",
    r"\bcreate\s+(?:an?\s+)?account\b",
    r"\bread\s+(?:more|the\s+full\s+story|the\s+rest)\b",
    r"\bcontinue\s+reading\b",
    r"\bshare\s+(?:this|on\s+twitter|on\s+facebook|via\s+email)\b",
    r"\bnewsletter\b",
    r"\brelated\s+(?:articles?|stories|posts?|reading|topics?|coverage)\b",
    r"\b(?:trending|most\s+(?:read|popular|viewed|shared))\b",
    r"\b(?:advertisement|sponsored\s+content|sponsored\s+by)\b",
    r"\bleave\s+a\s+comment\b",
    r"\b\d+\s+comments?\b",
    r"\bcookie\s+(?:policy|preferences|consent)\b",
    r"\bprivacy\s+policy\b",
    r"\b(?:terms\s+of\s+service|terms\s+(?:and|&)\s+conditions)\b",
    r"\ball\s+rights\s+reserved\b",
    r"©\s*\d{4}\b",
    r"\bcopyright\s+(?:\(c\)\s*)?\d{4}\b",
    r"\bprint\s+(?:this\s+)?(?:article|story|page)\b",
    r"\bemail\s+(?:this|the\s+author|to\s+a\s+friend)\b",
    r"\bfollow\s+(?:us|@\w+)\b",
    r"\b(?:tags?|filed\s+under|categories?|topics?)\s*:\s+\w",
    r"\b(?:photo|image|picture)\s+(?:by|courtesy|credit|caption)\b",
    r"\b(?:by\s+staff|staff\s+(?:writer|reporter)|editorial\s+board|"
    r"opinion\s+(?:editor|writer|columnist))\b",
    r"\b(?:updated|published|posted)\s+(?:on\s+)?"
    r"(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|\d{1,2}/\d{1,2}/\d{2,4})\b",
    r"\b\d+\s+min(?:ute)?\s+read\b",
    r"\bmore\s+from\s+\w+\b",
    r"\babout\s+(?:the\s+)?author\b",
    r"\b(?:donate|support\s+(?:our\s+)?(?:work|journalism|reporting))\b",
]
_WEBPAGE_GARBAGE_RE = re.compile(
    "|".join(f"(?:{p})" for p in _WEBPAGE_GARBAGE_PATTERNS),
    re.IGNORECASE,
)


def _has_headline_opening(text: str) -> bool:
    """Return True if the segment's first non-blank line looks like a
    news/article headline AND there's a substantive body after it.

    Tightening: only top-level markdown headings (`#` or `##`) or plain
    text headlines count. Sub-section headings (`###`+) are NOT
    headlines — those are common inside the user's own frameworks /
    chapter outlines. We also require body content after the heading,
    not just another heading.
    """
    if not text or len(text) < 250:
        return False  # below this size it's not a news article body
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False  # need a heading + something after it
    raw_first = lines[0].strip()
    # Sub-section markdown headings (`###`+) are NOT news headlines.
    if re.match(r"^#{3,}\s+", raw_first):
        return False
    # Strip leading top-level markdown hashes.
    line = re.sub(r"^#{1,2}\s+", "", raw_first)
    if not (8 <= len(line) <= 200):
        return False
    # First-person words disqualify (those are opinion/personal, not news).
    if re.search(r"\b(?:I|my|me|we|our|us)\b", line):
        return False
    # The line right after the headline should be a body paragraph
    # (not another heading or a single-word artifact).
    second = lines[1].strip()
    if re.match(r"^#{1,6}\s+", second):
        return False  # consecutive headings → likely a TOC or framework outline
    if len(second) < 40:
        return False  # too short to be a lede
    # Title-case OR all-caps.
    if _HEADLINE_ALL_CAPS_RE.match(line):
        return True
    if _HEADLINE_TITLE_CASE_RE.match(line):
        words = re.findall(r"\b[A-Za-z]{4,}\b", line)
        if not words:
            return False
        caps = sum(1 for w in words if w[0].isupper())
        if caps / len(words) >= 0.5:
            return True
    return False


def _count_webpage_garbage(text: str) -> int:
    """Count distinct webpage-boilerplate signals in the segment."""
    if not text:
        return 0
    return len(_WEBPAGE_GARBAGE_RE.findall(text))


# ---------------------------------------------------------------------------
# Platform-aware classification thresholds (2026-05-02)
# ---------------------------------------------------------------------------

# Per-platform min score to classify as news/opinion/resource. Set lower
# for Gemini (high prior of in-prompt pastes per user observation), higher
# for Claude (Claude segregates pastes via attachments — anything in the
# prompt body is much less likely to be a paste).
# Tightened 2026-05-02 after spot-check showed Gemini@0.30 was too
# permissive — short framework / outline pastes were classifying as news
# on weak signals (single markdown subheading). Raised Gemini to 0.42 so
# at least two distinct news signals must combine before classification.
_PLATFORM_NEWS_THRESHOLD = {
    "claude":   0.55,
    "chatgpt":  0.50,
    "gemini":   0.42,
    "local-ora": 0.55,
    "unknown":  0.50,
}
_PLATFORM_OPINION_THRESHOLD = {
    "claude":   0.55,
    "chatgpt":  0.50,
    "gemini":   0.42,
    "local-ora": 0.55,
    "unknown":  0.50,
}
# Resource classifications are stricter (technical / cite patterns are
# unambiguous regardless of platform).
_PLATFORM_RESOURCE_THRESHOLD = {
    "claude":   0.50,
    "chatgpt":  0.50,
    "gemini":   0.45,
    "local-ora": 0.50,
    "unknown":  0.50,
}


# ---------------------------------------------------------------------------
# Block segmentation
# ---------------------------------------------------------------------------


_BLANK_LINE_RE = re.compile(r"\n\s*\n")


def split_into_blocks(text: str) -> list[str]:
    """Split text on blank lines into block candidates."""
    if not text:
        return []
    blocks = _BLANK_LINE_RE.split(text)
    return [b for b in blocks if b.strip()]


def detect_paste_signals(block: str) -> list[str]:
    """Return list of paste-signal flags fired by this block."""
    flags: list[str] = []
    if _MD_HEADING_RE.search(block):
        flags.append("md-heading")
    if _CODE_FENCE_RE.search(block):
        flags.append("code-fence")
    if _BLOCKQUOTE_RE.search(block):
        flags.append("blockquote")
    bullets = len(_BULLET_LIST_RE.findall(block))
    if bullets >= 3:
        flags.append(f"bullet-list-{bullets}")
    elif bullets >= 1:
        flags.append("bullet-list-short")
    numbered = len(_NUMBERED_LIST_RE.findall(block))
    if numbered >= 3:
        flags.append(f"numbered-list-{numbered}")
    if _CITATION_PARENS_RE.search(block) or _CITATION_BRACKETS_RE.search(block):
        flags.append("citation-pattern")
    if _DOI_RE.search(block):
        flags.append("doi")
    if _BYLINE_RE.search(block):
        flags.append("byline")
    if _DATELINE_RE.search(block):
        flags.append("dateline")
    if len(block) >= _LONG_PASTE_THRESHOLD:
        # Long block with very few first-person references = likely pasted.
        first_person_hits = len(_FIRST_PERSON_RE.findall(block))
        word_count = max(len(block.split()), 1)
        density = first_person_hits / word_count
        if density < 0.02:
            flags.append("long-low-1stperson")
    return flags


# Strong signals — any one of these flips a block to pasted.
_STRONG_PASTE_FLAGS = frozenset({
    "md-heading", "code-fence", "blockquote",
    "citation-pattern", "doi", "byline", "dateline",
})


def is_block_pasted(block: str) -> tuple[bool, list[str]]:
    """Return (is_pasted, flags) for a block.

    A block is 'pasted' if any strong flag fires, or if it has multiple
    weaker flags (≥2 list-style or long-low-1stperson). Otherwise
    'personal'.
    """
    flags = detect_paste_signals(block)
    strong = [f for f in flags if any(s in f for s in _STRONG_PASTE_FLAGS)]
    if strong:
        return True, flags
    weak_score = 0
    for f in flags:
        if f.startswith("bullet-list-") and not f.endswith("-short"):
            weak_score += 1
        elif f.startswith("numbered-list-"):
            weak_score += 1
        elif f == "long-low-1stperson":
            weak_score += 2
    if weak_score >= 2:
        return True, flags
    return False, flags


# ---------------------------------------------------------------------------
# Smoothing — fix split paste segments
# ---------------------------------------------------------------------------


_PERSONAL_VOICE_PHRASES_RE = re.compile(
    r"\b(?:hey|hi|hello|please|thanks|thank\s+you|tell\s+me|"
    r"can\s+you|could\s+you|let\s+me\s+know|sorry|"
    r"i'?m|i\s+(?:think|want|need|feel|wonder|hope))\b",
    re.IGNORECASE,
)


def _has_personal_voice(block: str) -> bool:
    """Detect strong personal-voice markers — first-person density,
    conversational phrases, or short trailing question.

    A block with personal voice must NOT be smoothed into a paste run.
    """
    fp_hits = len(_FIRST_PERSON_RE.findall(block))
    word_count = max(len(block.split()), 1)
    if fp_hits / word_count >= 0.05:
        return True
    if _PERSONAL_VOICE_PHRASES_RE.search(block):
        return True
    # Short block that ends in '?' is conversational (direct question).
    stripped = block.strip()
    if stripped.endswith("?") and len(stripped) < 200:
        return True
    return False


def smooth_classifications(
    blocks: list[str],
    classifications: list[tuple[bool, list[str]]],
) -> list[tuple[bool, list[str]]]:
    """Reclassify 'personal' blocks that are continuations of paste runs.

    Rule: a block currently labeled 'personal' becomes 'pasted' if BOTH
      (a) it has no personal-voice markers, and
      (b) the previous block is 'pasted' AND (next is 'pasted' OR this is
          the last block).

    The intent: a paste typically splits across multiple paragraphs;
    body paragraphs without personal-voice markers should ride along
    with the paste they came from. The rule is asymmetric — leading
    personal lead-ins ("Here is the article:") stay personal because
    they have no preceding paste run.
    """
    out = list(classifications)
    n = len(blocks)
    for i in range(n):
        is_pasted, flags = out[i]
        if is_pasted:
            continue
        if _has_personal_voice(blocks[i]):
            continue
        prev_pasted = i > 0 and out[i - 1][0]
        next_pasted = i < n - 1 and out[i + 1][0]
        is_trailing = i == n - 1
        if prev_pasted and (next_pasted or is_trailing):
            out[i] = (True, sorted(set(flags + ["paste-continuation"])))
    return out


def merge_segments(blocks: list[str],
                    classifications: list[tuple[bool, list[str]]]
                    ) -> list[Segment]:
    """Merge adjacent same-kind blocks into Segment records."""
    segments: list[Segment] = []
    if not blocks:
        return segments
    cur_kind = "pasted" if classifications[0][0] else "personal"
    cur_blocks: list[str] = [blocks[0]]
    cur_flags: list[str] = list(classifications[0][1])
    cur_first_idx = 0
    cur_last_idx = 0
    for i in range(1, len(blocks)):
        is_pasted, flags = classifications[i]
        kind = "pasted" if is_pasted else "personal"
        if kind == cur_kind:
            cur_blocks.append(blocks[i])
            cur_flags.extend(flags)
            cur_last_idx = i
        else:
            segments.append(Segment(
                kind=cur_kind,
                content="\n\n".join(cur_blocks),
                block_indices=(cur_first_idx, cur_last_idx),
                heuristic_flags=sorted(set(cur_flags)) if cur_kind == "pasted" else [],
            ))
            cur_kind = kind
            cur_blocks = [blocks[i]]
            cur_flags = list(flags)
            cur_first_idx = i
            cur_last_idx = i
    segments.append(Segment(
        kind=cur_kind,
        content="\n\n".join(cur_blocks),
        block_indices=(cur_first_idx, cur_last_idx),
        heuristic_flags=sorted(set(cur_flags)) if cur_kind == "pasted" else [],
    ))
    return segments


def segment_user_input(text: str) -> list[Segment]:
    """Top-level segmentation: split + classify + smooth + merge."""
    blocks = split_into_blocks(text)
    if not blocks:
        return []
    classifications = [is_block_pasted(b) for b in blocks]
    classifications = smooth_classifications(blocks, classifications)
    return merge_segments(blocks, classifications)


# ---------------------------------------------------------------------------
# 4-bucket classification of pasted segments
# ---------------------------------------------------------------------------


def _score_news(text: str, flags: list[str]) -> float:
    """Score a segment's news-piece likelihood on [0, 1].

    Strong signals:
      - Headline opening (capitalized title at segment start) +
        substantive body — implemented in `_has_headline_opening`
      - Webpage garbage (Subscribe / Sign in / Related articles / etc.)
      - Headline + ≥2 garbage hits → near-certain news scrape
    Plus the original byline / dateline / attributed-quote signals.

    A news article must be at least ~500 chars; shorter segments are
    almost certainly something else (a tagline, a sub-heading, etc.).
    """
    if len(text) < 500:
        return 0.0   # too short to be a news article
    score = 0.0
    has_headline = _has_headline_opening(text)
    garbage_hits = _count_webpage_garbage(text)
    # Headline + garbage combo is the strongest news signal — most
    # webpage scrapes drag both. Either alone is moderate.
    if has_headline:
        score += 0.35
    if garbage_hits >= 1:
        score += 0.15
    if garbage_hits >= 2:
        score += 0.15
    if garbage_hits >= 4:
        score += 0.15
    if has_headline and garbage_hits >= 2:
        score += 0.20   # combo bonus
    # Original signals retained.
    if "byline" in flags:
        score += 0.25
    if "dateline" in flags:
        score += 0.25
    if _ATTRIBUTED_QUOTE_RE.search(text):
        score += 0.10
    return min(score, 1.0)


def _score_opinion(text: str, flags: list[str]) -> float:
    score = 0.0
    opinion_hits = len(_OPINION_FRAME_RE.findall(text))
    if opinion_hits >= 1:
        score += 0.4 + min(opinion_hits, 3) * 0.1
    fp_hits = len(_FIRST_PERSON_RE.findall(text))
    word_count = max(len(text.split()), 1)
    density = fp_hits / word_count
    if density >= 0.04:
        score += 0.3
    if "byline" in flags and density >= 0.02:
        # Bylined first-person → strong opinion signal.
        score += 0.2
    return min(score, 1.0)


def _score_resource(text: str, flags: list[str]) -> float:
    score = 0.0
    if "citation-pattern" in flags:
        score += 0.35
    if "doi" in flags:
        score += 0.25
    if _ET_AL_RE.search(text):
        score += 0.15
    if _RESEARCH_SECTIONS_RE.search(text):
        score += 0.25
    if len(text) >= _RESOURCE_MIN_CHARS:
        score += 0.1
    return min(score, 1.0)


def _vault_lookup(segment_content: str, vault_index: dict,
                   min_overlap: float = 0.5) -> Optional[dict]:
    """Return best vault match for this segment, or None.

    Lazy-imports vault_indexer to avoid circular dependency at import.
    """
    if not vault_index or not vault_index.get("entries"):
        return None
    from orchestrator.tools.vault_indexer import find_matches_by_paragraph_hash
    matches = find_matches_by_paragraph_hash(
        segment_content, vault_index, min_overlap=min_overlap, mature_only=False,
    )
    if not matches:
        return None
    return matches[0]   # already sorted by overlap descending


def classify_pasted_segment(segment: Segment,
                              vault_index: Optional[dict] = None,
                              vault_overlap_threshold: float = 0.5,
                              source_platform: str = "unknown") -> Segment:
    """Fill in classification + vault_match + confidence on a pasted segment.

    Vault lookup runs first; if a mature-version match is found the
    segment is classified `earlier-draft` and the heuristic scoring
    is skipped. Otherwise the news / opinion / resource scores are
    computed and the highest wins above a per-platform threshold.
    Ties or all-low scores → 'other'.

    `source_platform` adjusts the news/opinion threshold per the user's
    observation that Gemini sessions inline pastes (high prior), Claude
    segregates them (low prior), and ChatGPT is era-dependent.
    """
    if segment.kind != "pasted":
        return segment

    # 1. Vault index lookup → earlier-draft override.
    if vault_index is not None:
        match = _vault_lookup(segment.content, vault_index,
                                min_overlap=vault_overlap_threshold)
        if match:
            segment.classification = "earlier-draft"
            segment.confidence = float(match.get("overlap_ratio", 0.0))
            segment.vault_match = {
                "id":           match["entry"].get("id"),
                "vault_path":   match["entry"].get("vault_path"),
                "title":        match["entry"].get("title"),
                "mature":       match["entry"].get("mature"),
                "overlap_ratio": match["overlap_ratio"],
            }
            return segment

    # 2. Heuristic scoring.
    news_score     = _score_news(segment.content, segment.heuristic_flags)
    opinion_score  = _score_opinion(segment.content, segment.heuristic_flags)
    resource_score = _score_resource(segment.content, segment.heuristic_flags)

    # Per-platform thresholds. Gemini gets a much lower bar for
    # news/opinion since the user observed pastes nearly always landed
    # in-prompt there.
    platform_key = (source_platform or "unknown").lower()
    news_thresh    = _PLATFORM_NEWS_THRESHOLD.get(platform_key, 0.45)
    opinion_thresh = _PLATFORM_OPINION_THRESHOLD.get(platform_key, 0.45)
    resource_thresh = _PLATFORM_RESOURCE_THRESHOLD.get(platform_key, 0.50)

    # Headline + ≥2 webpage-garbage hits force news classification —
    # this combo is the user's stated definitive signal and overrides
    # any other scoring.
    if _has_headline_opening(segment.content) \
            and _count_webpage_garbage(segment.content) >= 2:
        segment.classification = "news"
        segment.confidence = max(news_score, 0.85)
        if "headline-garbage-combo" not in segment.heuristic_flags:
            segment.heuristic_flags = sorted(set(
                list(segment.heuristic_flags) + ["headline-garbage-combo"]
            ))
        return segment

    candidates: list[tuple[str, float, float]] = [
        ("news",     news_score,     news_thresh),
        ("opinion",  opinion_score,  opinion_thresh),
        ("resource", resource_score, resource_thresh),
    ]
    qualifying = [(label, score) for label, score, t in candidates
                   if score >= t]
    if qualifying:
        # Pick the highest-scoring qualifying class.
        qualifying.sort(key=lambda x: -x[1])
        best_label, best_score = qualifying[0]
        segment.classification = best_label
        segment.confidence = best_score
    else:
        # Best-of-class score still recorded for downstream tuning.
        best_label_overall = max(candidates, key=lambda c: c[1])
        segment.classification = "other"
        segment.confidence = best_label_overall[1]
    return segment


def process_user_input(text: str,
                        vault_index: Optional[dict] = None,
                        vault_overlap_threshold: float = 0.5,
                        source_platform: str = "unknown") -> list[Segment]:
    """Full Phase 1.3 pipeline: segment + classify + vault lookup.

    For 'personal' segments, also run vault lookup — pasted material
    containing first-person dialogue (e.g. fiction with character speech)
    can fool the personal-voice heuristic. If such a segment overlaps a
    vault entry it gets reclassified to pasted/earlier-draft.

    `source_platform` is plumbed through to `classify_pasted_segment`
    for platform-aware thresholds (Gemini lower bar, Claude higher).
    """
    segments = segment_user_input(text)
    for seg in segments:
        if seg.kind == "pasted":
            classify_pasted_segment(seg, vault_index=vault_index,
                                     vault_overlap_threshold=vault_overlap_threshold,
                                     source_platform=source_platform)
        elif seg.kind == "personal" and vault_index is not None:
            match = _vault_lookup(seg.content, vault_index,
                                    min_overlap=vault_overlap_threshold)
            if match:
                seg.kind = "pasted"
                seg.classification = "earlier-draft"
                seg.confidence = float(match.get("overlap_ratio", 0.0))
                seg.vault_match = {
                    "id":             match["entry"].get("id"),
                    "vault_path":     match["entry"].get("vault_path"),
                    "title":          match["entry"].get("title"),
                    "mature":         match["entry"].get("mature"),
                    "overlap_ratio":  match["overlap_ratio"],
                }
                seg.heuristic_flags = sorted(set(
                    list(seg.heuristic_flags) + ["vault-match-reclassified"]
                ))
    # Adjacent same-classification segments now merge — but only if their
    # classifications AND vault matches agree. Cross-class boundaries are
    # preserved so a paste with mixed earlier-draft + other paragraphs keeps
    # the per-section vault metadata intact.
    return _final_merge_segments(segments)


def _final_merge_segments(segments: list[Segment]) -> list[Segment]:
    """Merge adjacent segments whose classification + vault match agree."""
    if not segments:
        return segments
    out: list[Segment] = [segments[0]]
    for seg in segments[1:]:
        prev = out[-1]
        # Same kind required.
        if seg.kind != prev.kind:
            out.append(seg)
            continue
        # For pasted: classification + vault id must both match.
        if seg.kind == "pasted":
            same_class = seg.classification == prev.classification
            prev_vault_id = (prev.vault_match or {}).get("id")
            seg_vault_id = (seg.vault_match or {}).get("id")
            same_vault = prev_vault_id == seg_vault_id
            if not (same_class and same_vault):
                out.append(seg)
                continue
        # Merge.
        prev.content = prev.content + "\n\n" + seg.content
        prev.block_indices = (prev.block_indices[0], seg.block_indices[1])
        prev.heuristic_flags = sorted(set(
            list(prev.heuristic_flags) + list(seg.heuristic_flags)
        ))
        # Confidence: keep higher of the two.
        prev.confidence = max(prev.confidence, seg.confidence)
    return out


__all__ = [
    "Segment",
    "split_into_blocks",
    "detect_paste_signals",
    "is_block_pasted",
    "merge_segments",
    "segment_user_input",
    "classify_pasted_segment",
    "process_user_input",
]
