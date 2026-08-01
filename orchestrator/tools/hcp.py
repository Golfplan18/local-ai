"""
hcp.py — Hierarchical Context Protocol for long-form document ingestion.

Canonical spec: `~/Documents/vault/Projects/Ora/Specification — Hierarchical
Context Protocol.md` (created 2026-07-11 from the recovered 2026-04-11 dictation).
Long complex works (books, long frameworks, paper syntheses, extended
outlines) are chunked with a layered context block PREPENDED to each chunk,
so a chunk retrieved in isolation still carries the meaning its position in
the argument gives it.

Ingestion is two-pass:

  Pass 1 — structure extraction (`build_structural_index`): read the whole
  document, map the heading hierarchy, and produce one-sentence summaries
  at each level (model-generated when a call_fn is provided, first-paragraph
  heuristic otherwise). This structural index is the source material for
  context levels 1-4 — prepends are always generated from it, never
  hand-written.

  Pass 2 — chunk creation with context injection (`chunk_with_context`):
  chunk at section boundaries (paragraph boundaries inside oversized
  sections), then prepend context levels. Two passes are required because
  Level 5 needs the ACTUAL adjacent chunks' text, which doesn't exist until
  all chunks are cut.

Six context levels:
  1. Positional breadcrumb  — [POSITION] path through the work's hierarchy
  2. Work-level thesis      — [THESIS] the document's thesis, one sentence
  3. Part/chapter arguments — [CONTEXT] one sentence per ancestor level
  4. Section point          — [SECTION] the containing section's point
  5. Local continuity       — [PRECEDING] closing 1-2 sentences of the
                              preceding chunk; [FOLLOWING] opening 1-2
                              sentences of the following chunk
  6. Role declaration       — [ROLE] the chunk's function in the argument
                              (premise / evidence / counterargument /
                              conclusion / implication)

Similarity-scaled prepend depth (ALL thresholds are PROVISIONAL tuning
constants — judgment-set, not calibrated; retune freely):
  >= SIMILARITY_FULL (0.90)      — all six levels
  SIMILARITY_MID  (0.75) - 0.89  — levels 1-4
  <  SIMILARITY_MID              — levels 1-2 (compressed floor)

NO CHUNK IS EVER DROPPED. A low-similarity chunk stays retrievable with the
compressed breadcrumb+thesis prepend. (An earlier skeleton discarded chunks
scoring below 0.60 — that silent loss was a spec violation, corrected
2026-07-11.)

The quality gate (`verify_prepends`) checks that prepends were generated
before a document is marked processed. Per the standing no-stop-gates rule
it FAILS OPEN: failures are logged loudly to stderr and recorded on the
report, but chunks are always returned and nothing is blocked.

Usage:
    from orchestrator.tools.hcp import HCPProcessor
    processor = HCPProcessor()
    index = processor.build_structural_index(markdown_text)
    chunks = processor.chunk_with_context(markdown_text, index)
    # or both passes + quality gate in one call:
    chunks = processor.process(markdown_text)

Module-level functions (`build_structural_index`, `chunk_with_context`,
`process_long_form`, `format_chunk_for_extraction`) remain the stable API
for pipeline callers (see batch_processor.py, knowledge_index.py).
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# PROVISIONAL TUNING CONSTANTS — set by judgment, not calibration.
# Retune freely; none is load-bearing by design.
# ---------------------------------------------------------------------------

DEFAULT_MAX_CHUNK_TOKENS = 2000   # provisional — target chunk size
CHARS_PER_TOKEN = 4               # provisional — rough token-estimate divisor
SIMILARITY_FULL = 0.90            # provisional — all six levels at/above this
SIMILARITY_MID = 0.75             # provisional — levels 1-4 at/above this
SIMILARITY_LOW = 0.60             # provisional — historical band floor; kept
                                  #   for reference. Below SIMILARITY_MID the
                                  #   prepend compresses to levels 1-2; chunks
                                  #   are NEVER dropped at any similarity.
CONTINUITY_SENTENCES = 2          # provisional — excerpt length per side
CONTINUITY_MAX_CHARS = 400        # provisional — hard cap per excerpt


@dataclass
class Section:
    """A section in the document hierarchy."""
    level: int          # heading level (1-6)
    title: str          # heading text
    start_line: int     # line index in source
    end_line: int       # line index of subtree end (incl. subsections)
    argument: str = ""  # one-sentence summary (populated during indexing)
    parent_idx: int | None = None  # index into sections list


@dataclass
class StructuralIndex:
    """The structural index of a document — Pass 1 output, and the source
    material for context levels 1-4."""
    document_title: str
    document_thesis: str
    total_sections: int
    estimated_tokens: int
    sections: list[Section] = field(default_factory=list)


@dataclass
class HCPChunk:
    """A chunk with HCP context levels prepended."""
    content: str                # the raw chunk text
    context_prefix: str         # the HCP context to prepend
    section_path: str           # breadcrumb path (e.g., "Part II > Chapter 4 > Section 4.2")
    similarity_score: float     # similarity to document theme (for scaling)
    context_levels_included: int  # how many of the 6 levels were included
    start_line: int
    end_line: int
    chunk_index: int = 0        # 1-based position in the document's chunk list
    total_chunks: int = 0
    role: str = ""              # Level 6 role declaration (bare, no [ROLE] tag)
    preceding_excerpt: str = ""  # Level 5 source excerpts (bare)
    following_excerpt: str = ""


@dataclass
class HCPQualityReport:
    """Quality-gate result. `ok=False` never blocks anything — the gate
    fails OPEN with loud logging; the operator decides."""
    ok: bool
    issues: list[str] = field(default_factory=list)
    chunk_count: int = 0
    levels_histogram: dict[int, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pass 1 — structural index builder
# ---------------------------------------------------------------------------

def build_structural_index(markdown_text: str, call_fn=None, endpoint=None) -> StructuralIndex:
    """
    Pass 1: build a structural index of a long-form document.

    The index identifies the document's hierarchical structure, extracts
    one-sentence section arguments, and estimates the thesis.

    Args:
        markdown_text: The full document in markdown format.
        call_fn: Optional model call function for thesis/argument extraction.
                 If None, uses heuristic extraction (first paragraph).
        endpoint: Model endpoint for call_fn.

    Returns:
        StructuralIndex with sections and arguments populated.
    """
    lines = markdown_text.split('\n')
    sections = []
    fence = _fence_mask(lines)

    # Parse heading structure. A '#'-prefixed comment line inside a fenced
    # code block is not a document heading — skip fenced lines, or an
    # in-fence '# comment' would be parsed as a real section and split the
    # fence in half (and would become the false parent of whatever real
    # heading follows it).
    for i, line in enumerate(lines):
        if fence[i]:
            continue
        heading_match = re.match(r'^(#{1,6})\s+(.+)', line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            sections.append(Section(
                level=level,
                title=title,
                start_line=i,
                end_line=len(lines),  # will be corrected below
            ))

    # Set end_line for each section (subtree ends at the next section of
    # the same or higher level)
    for idx in range(len(sections)):
        current_level = sections[idx].level
        for next_idx in range(idx + 1, len(sections)):
            if sections[next_idx].level <= current_level:
                sections[idx].end_line = sections[next_idx].start_line
                break

    # Set parent references
    for idx in range(len(sections)):
        current_level = sections[idx].level
        # Walk backward to find nearest parent (lower heading level)
        for prev_idx in range(idx - 1, -1, -1):
            if sections[prev_idx].level < current_level:
                sections[idx].parent_idx = prev_idx
                break

    # Extract document title (first H1 or first heading)
    doc_title = ""
    for s in sections:
        if s.level == 1:
            doc_title = s.title
            break
    if not doc_title and sections:
        doc_title = sections[0].title

    estimated_tokens = _estimate_tokens(markdown_text)

    # Extract arguments for each section
    if call_fn and endpoint:
        _extract_arguments_with_model(sections, lines, call_fn, endpoint)
    else:
        _extract_arguments_heuristic(sections, lines)

    # Extract thesis (first section's argument or document-level summary)
    thesis = ""
    for s in sections:
        if s.level <= 2 and s.argument:
            thesis = s.argument
            break
    if not thesis:
        thesis = _extract_first_paragraph(lines)

    return StructuralIndex(
        document_title=doc_title,
        document_thesis=thesis,
        total_sections=len(sections),
        estimated_tokens=estimated_tokens,
        sections=sections,
    )


def _extract_arguments_heuristic(sections: list[Section], lines: list[str]):
    """Extract section arguments using the first substantive paragraph."""
    for section in sections:
        start = section.start_line + 1  # skip the heading line
        end = section.end_line
        content_lines = []

        for i in range(start, min(end, start + 20)):  # look at first 20 lines max
            line = lines[i].strip() if i < len(lines) else ""
            if not line:
                if content_lines:
                    break  # end of first paragraph
                continue
            if re.match(r'^#{1,6}\s+', line):
                break  # hit a sub-heading
            content_lines.append(line)

        if content_lines:
            argument = ' '.join(content_lines)
            if len(argument) > 200:
                argument = argument[:197] + "..."
            section.argument = argument


def _extract_arguments_with_model(sections: list[Section], lines: list[str],
                                   call_fn, endpoint):
    """Use a model to extract section arguments (one-sentence summaries)."""
    sections_text = ""
    for i, section in enumerate(sections[:30]):  # limit to 30 sections
        start = section.start_line + 1
        end = min(section.end_line, start + 10)
        preview = '\n'.join(lines[start:end]).strip()[:300]
        sections_text += f"\n### Section {i+1}: {section.title}\n{preview}\n"

    messages = [
        {"role": "system", "content": "You are a document analysis assistant. For each section below, provide a one-sentence argument or claim that the section makes. Output as numbered lines matching the section numbers."},
        {"role": "user", "content": f"Summarize each section's argument:\n{sections_text}"},
    ]

    try:
        response = call_fn(messages, endpoint)
    except Exception as e:
        print(f"HCP: model argument extraction failed ({type(e).__name__}: {e}) "
              f"— falling back to heuristic extraction.", file=sys.stderr)
        response = None
    if response:
        for line in response.split('\n'):
            match = re.match(r'(?:Section\s+)?(\d+)\s*[:.)]\s*(.+)', line.strip())
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(sections):
                    sections[idx].argument = match.group(2).strip()

    # Fill in any gaps with heuristic
    for section in sections:
        if not section.argument:
            _extract_arguments_heuristic([section], lines)


def _extract_first_paragraph(lines: list[str]) -> str:
    """Extract the first substantive paragraph from lines."""
    content_lines = []
    started = False

    for line in lines:
        stripped = line.strip()
        if re.match(r'^#{1,6}\s+', stripped):
            if started:
                break
            continue
        if re.match(r'^---\s*$', stripped):
            continue
        if not stripped:
            if started:
                break
            continue
        started = True
        content_lines.append(stripped)

    text = ' '.join(content_lines)
    if len(text) > 300:
        text = text[:297] + "..."
    return text


# ---------------------------------------------------------------------------
# Pass 2 — chunk creation with context injection
# ---------------------------------------------------------------------------

@dataclass
class _RawChunk:
    """Pass-2 intermediate: a cut chunk before context injection."""
    content: str
    section: Section
    ordinal_in_section: int
    start_line: int
    end_line: int


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


_FENCE_RE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')


def _fence_mask(lines: list[str]) -> list[bool]:
    """True for each line inside (or itself delimiting) a fenced code
    block. Heuristic — toggles on any line matching a triple-backtick or
    triple-tilde fence marker (<=3 leading spaces, per CommonMark) without
    verifying the closing fence matches the opening character/length.
    Enough to keep an in-fence '#'-prefixed comment line from being read
    as markdown structure."""
    mask = [False] * len(lines)
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            mask[i] = True  # the fence delimiter line itself
            in_fence = not in_fence
        else:
            mask[i] = in_fence
    return mask


def _is_heading(line: str) -> bool:
    """ATX heading syntax at column 0 — matches build_structural_index's
    own heading regex exactly (unstripped). An indented '#'-prefixed line
    is code/quoted text, not a heading; stripping leading whitespace
    before matching (the prior behavior) misclassified indented content
    as heading-only and silently dropped it."""
    return bool(re.match(r'^#{1,6}\s+.+', line))


def _non_heading_lines(lines: list[str]) -> list[str]:
    """Lines that count as real content for 'is this region/chunk
    heading-only' checks: non-blank, and not a genuine ATX heading. A
    line inside a fenced code block always counts as content — even one
    that is syntactically heading-shaped (e.g. a '# comment' at column 0
    inside a ```python fence) — since fence state overrides heading
    shape. Single source of truth so the region-emptiness gate, prose
    extraction, and the quality-gate coverage check all agree on what
    counts as a heading."""
    fence = _fence_mask(lines)
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if fence[i] or not _is_heading(line):
            out.append(line)
    return out


def _chunk_regions(lines: list[str], index: StructuralIndex) -> list[tuple[Section, int, int]]:
    """Leaf content regions covering the document exactly once.

    Each section's region runs from its heading to the start of the NEXT
    heading of ANY level — NOT to its subtree end. Using subtree ends here
    would put a parent section's child content in the parent's region AND
    in each child's, chunking the same text twice. Text before the first
    heading, and heading-less documents, get a synthetic root region so no
    content is ever lost.
    """
    sections = index.sections
    if not sections:
        synthetic = Section(level=1, title=index.document_title or "Document",
                            start_line=0, end_line=len(lines))
        return [(synthetic, 0, len(lines))]

    regions: list[tuple[Section, int, int]] = []
    if sections[0].start_line > 0:
        preamble = Section(level=1,
                           title=index.document_title or "Document opening",
                           start_line=0, end_line=sections[0].start_line)
        regions.append((preamble, 0, sections[0].start_line))
    for i, s in enumerate(sections):
        own_end = sections[i + 1].start_line if i + 1 < len(sections) else len(lines)
        regions.append((s, s.start_line, own_end))
    return regions


def _raw_chunks_for_region(lines: list[str], section: Section,
                           start: int, end: int,
                           max_chunk_tokens: int) -> list[_RawChunk]:
    """Cut one region into raw chunks: whole-region if it fits, paragraph
    accumulation otherwise. Paragraph separation (blank lines) is preserved
    inside a chunk. A single paragraph larger than the budget is emitted
    whole — oversized beats dropped."""
    region_lines = lines[start:end]
    if not _non_heading_lines(region_lines):
        return []  # heading-only region — the title travels in breadcrumbs

    region_text = '\n'.join(region_lines).strip('\n')
    if _estimate_tokens(region_text) <= max_chunk_tokens:
        return [_RawChunk(content=region_text, section=section,
                          ordinal_in_section=0, start_line=start, end_line=end)]

    # Group region lines into paragraphs (blank-line separated), tracking
    # line offsets so start/end lines stay accurate.
    paragraphs: list[tuple[list[str], int]] = []
    current: list[str] = []
    current_off = None
    for off, line in enumerate(region_lines):
        if not line.strip():
            if current:
                paragraphs.append((current, current_off))
                current, current_off = [], None
        else:
            if current_off is None:
                current_off = off
            current.append(line)
    if current:
        paragraphs.append((current, current_off))

    chunks: list[_RawChunk] = []
    acc: list[str] = []          # accumulated paragraph texts
    acc_start = None
    acc_end = None
    acc_tokens = 0

    def _emit():
        nonlocal acc, acc_start, acc_end, acc_tokens
        if acc:
            chunks.append(_RawChunk(
                content='\n\n'.join(acc), section=section,
                ordinal_in_section=len(chunks),
                start_line=start + acc_start, end_line=start + acc_end))
            acc, acc_start, acc_end, acc_tokens = [], None, None, 0

    for para_lines, off in paragraphs:
        para_text = '\n'.join(para_lines)
        para_tokens = _estimate_tokens(para_text)
        # Don't flush an accumulator that is still heading-only (e.g. just
        # the section's own heading line, queued before its first body
        # paragraph) purely because the NEXT paragraph would overflow the
        # budget — that would emit a heading-only raw chunk, which
        # _prose_text() reduces to "", silently emptying the Level 5
        # continuity excerpt for whichever neighbor sits beside it. Let
        # the heading merge into the same chunk as the oversized paragraph
        # that follows it instead.
        if (acc and acc_tokens + para_tokens > max_chunk_tokens
                and _non_heading_lines("\n".join(acc).split("\n"))):
            _emit()
        if acc_start is None:
            acc_start = off
        acc.append(para_text)
        acc_end = off + len(para_lines)
        acc_tokens += para_tokens
    _emit()

    return chunks


# --- Level 5 helpers — local narrative continuity ---------------------------

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _prose_text(chunk_text: str) -> str:
    """Chunk text flattened to prose: headings and blank lines dropped
    (fence-aware — see _non_heading_lines)."""
    lines = _non_heading_lines(chunk_text.split('\n'))
    return ' '.join(l.strip() for l in lines)


def _closing_sentences(chunk_text: str,
                       n: int = CONTINUITY_SENTENCES,
                       max_chars: int = CONTINUITY_MAX_CHARS) -> str:
    prose = _prose_text(chunk_text)
    if not prose:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(prose) if s.strip()]
    excerpt = ' '.join(sentences[-n:]) if sentences else prose
    return excerpt[-max_chars:].strip()


def _opening_sentences(chunk_text: str,
                       n: int = CONTINUITY_SENTENCES,
                       max_chars: int = CONTINUITY_MAX_CHARS) -> str:
    prose = _prose_text(chunk_text)
    if not prose:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(prose) if s.strip()]
    excerpt = ' '.join(sentences[:n]) if sentences else prose
    return excerpt[:max_chars].strip()


# --- Level 6 helper — role declaration ---------------------------------------

# Marker-count classification is a PROVISIONAL heuristic — a lightweight
# model would classify roles more faithfully; wire that in when per-chunk
# model calls are acceptable at ingest time.
_ROLE_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("states a conclusion",
     ("therefore", "in conclusion", "thus,", "in sum", "consequently",
      "the upshot")),
    ("introduces a counterargument",
     ("however", "critics", "objection", "on the other hand", "skeptic",
      "counterargument", "pushes back", "one might object")),
    ("provides evidence",
     ("for example", "for instance", "study", "studies", "the data",
      "evidence", "measured", "results show", "found that")),
    ("draws an implication",
     ("this means", "implies", "it follows", "suggests that")),
]


def _declare_role(content: str, is_first_in_section: bool) -> str:
    """One-sentence-fragment role declaration: what function this chunk
    serves in its parent section's argument."""
    low = content.lower()
    best = ""
    best_count = 0
    for label, markers in _ROLE_MARKERS:
        count = sum(low.count(m) for m in markers)
        if count > best_count:
            best, best_count = label, count
    if not best:
        best = ("establishes a premise" if is_first_in_section
                else "develops the section's argument")
    return best


# --- Similarity scoring -------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _as_float_list(vec) -> list[float]:
    return vec.tolist() if hasattr(vec, "tolist") else list(vec)


def make_similarity_scorer(thesis: str):
    """Return similarity(chunk_text) -> float in [0, 1] against the thesis.

    Uses the canonical embedder (orchestrator.embedding, Ollama-backed) with
    cosine similarity mapped from [-1, 1] to [0, 1]. Falls back to the
    keyword-overlap heuristic when the embedder is unreachable. Both the
    cosine mapping and the downstream similarity bands are PROVISIONAL —
    calibrate against real retrieval behavior before trusting the bands.
    """
    thesis_vec = None
    embed_fn = None
    if thesis:
        try:
            from orchestrator.embedding import get_embedding_function
            embed_fn = get_embedding_function()
            result = embed_fn([thesis])
            thesis_vec = _as_float_list(result[0]) if result else None
        except Exception:
            thesis_vec = None

    def score(chunk_text: str) -> float:
        if thesis_vec is not None and embed_fn is not None:
            try:
                result = embed_fn([chunk_text[:4000]])
                if result:
                    cos = _cosine(thesis_vec, _as_float_list(result[0]))
                    return max(0.0, min(1.0, (cos + 1.0) / 2.0))
            except Exception:
                pass  # embedder hiccup — heuristic fallback below
        return _estimate_similarity(chunk_text, thesis)

    return score


def _estimate_similarity(chunk_text: str, thesis: str) -> float:
    """Keyword-overlap fallback when no embedder is reachable. PROVISIONAL —
    kept only as the degraded path; the scaled output range (0.5-1.0) is a
    judgment call, not a calibrated mapping."""
    if not thesis:
        return 0.80  # default — include with partial context

    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "must", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "and",
        "but", "or", "nor", "not", "no", "so", "if", "then", "than",
        "that", "this", "these", "those", "it", "its", "they", "their",
    }

    def tokenize(text):
        words = re.findall(r'\b[a-z]+\b', text.lower())
        return set(w for w in words if w not in stop_words and len(w) > 2)

    thesis_tokens = tokenize(thesis)
    chunk_tokens = tokenize(chunk_text[:1000])

    if not thesis_tokens:
        return 0.80

    overlap = thesis_tokens & chunk_tokens
    score = len(overlap) / len(thesis_tokens)

    # Scale to 0.5-1.0 range (pure keyword overlap rarely exceeds 0.5)
    return min(1.0, 0.5 + score)


def _levels_for_similarity(similarity: float) -> int:
    """Similarity band -> prepend depth. Bands are PROVISIONAL. The floor
    is 2 (breadcrumb + thesis) — never 0; chunks are never dropped."""
    if similarity >= SIMILARITY_FULL:
        return 6
    if similarity >= SIMILARITY_MID:
        return 4
    return 2


# --- Context prefix assembly ---------------------------------------------------

def _breadcrumb(section: Section, index: StructuralIndex) -> str:
    path_parts = [section.title]
    current = section
    while current.parent_idx is not None:
        parent = index.sections[current.parent_idx]
        path_parts.insert(0, parent.title)
        current = parent
    return " > ".join(path_parts)


def _ancestor_chain(section: Section, index: StructuralIndex) -> list[Section]:
    """Ancestors of `section`, topmost first (excluding the section itself)."""
    chain: list[Section] = []
    current = section
    while current.parent_idx is not None:
        parent = index.sections[current.parent_idx]
        chain.insert(0, parent)
        current = parent
    return chain


def _build_context_prefix(chunk: _RawChunk, index: StructuralIndex,
                          section_path: str, levels: int,
                          preceding_excerpt: str, following_excerpt: str,
                          role: str) -> str:
    """Assemble the prepended context block for one chunk."""
    parts = []

    # Level 1 — positional breadcrumb (always travels)
    parts.append(f"[POSITION] {section_path}")

    # Level 2 — work-level thesis (always travels)
    if levels >= 2 and index.document_thesis:
        parts.append(f"[THESIS] {index.document_thesis}")

    # Level 3 — part/chapter arguments: one line per ancestor level
    if levels >= 3:
        for ancestor in _ancestor_chain(chunk.section, index):
            if ancestor.argument and ancestor.argument != index.document_thesis:
                parts.append(f"[CONTEXT] {ancestor.title}: {ancestor.argument}")

    # Level 4 — the containing section's own point
    if levels >= 4:
        if chunk.section.argument and chunk.section.argument != index.document_thesis:
            parts.append(f"[SECTION] {chunk.section.title}: {chunk.section.argument}")

    # Level 5 — local narrative continuity from the ACTUAL adjacent chunks
    if levels >= 5:
        if preceding_excerpt:
            parts.append(f"[PRECEDING] …{preceding_excerpt}")
        if following_excerpt:
            parts.append(f"[FOLLOWING] {following_excerpt}…")

    # Level 6 — role declaration
    if levels >= 6 and role:
        parts.append(f"[ROLE] This chunk {role} within '{chunk.section.title}'.")

    return "\n".join(parts)


def chunk_with_context(markdown_text: str, index: StructuralIndex,
                       max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
                       similarity_fn=None) -> list[HCPChunk]:
    """
    Pass 2: chunk a long-form document and inject HCP context levels.

    Chunks are cut at section boundaries (paragraph boundaries inside
    oversized sections), covering the document exactly once — including
    text before the first heading and heading-less documents. Then each
    chunk gets its context block: breadcrumb and thesis always; deeper
    levels per the similarity bands; Level 5 continuity drawn from the
    ACTUAL neighboring chunks' text (this is why chunking completes before
    any prepend is written).

    Args:
        markdown_text: The full document markdown.
        index: The structural index from build_structural_index() (Pass 1).
        max_chunk_tokens: PROVISIONAL chunk-size target (approximate).
        similarity_fn: Optional callable(chunk_text) -> float in [0, 1].
            Defaults to embedding cosine vs. the thesis, with the
            keyword-overlap heuristic as the degraded path.

    Returns:
        List of HCPChunk — every chunk of the document; none are dropped.
    """
    lines = markdown_text.split('\n')

    raw_chunks: list[_RawChunk] = []
    for section, start, end in _chunk_regions(lines, index):
        raw_chunks.extend(
            _raw_chunks_for_region(lines, section, start, end, max_chunk_tokens))

    if similarity_fn is None:
        similarity_fn = make_similarity_scorer(index.document_thesis)

    total = len(raw_chunks)
    chunks: list[HCPChunk] = []
    for i, raw in enumerate(raw_chunks):
        section_path = _breadcrumb(raw.section, index)
        try:
            similarity = similarity_fn(raw.content)
        except Exception as e:
            # A raising scorer (custom or a future broken default) must
            # never cost the document its chunks — fail toward the
            # compressed floor, not toward losing the chunk.
            print(f"HCP: similarity_fn raised for a chunk "
                  f"({type(e).__name__}: {e}) — using the compressed "
                  f"floor so the chunk is not lost.", file=sys.stderr)
            similarity = 0.0
        levels = _levels_for_similarity(similarity)

        preceding = _closing_sentences(raw_chunks[i - 1].content) if i > 0 else ""
        following = _opening_sentences(raw_chunks[i + 1].content) if i + 1 < total else ""
        role = _declare_role(raw.content, raw.ordinal_in_section == 0)

        context_prefix = _build_context_prefix(
            raw, index, section_path, levels, preceding, following, role)

        chunks.append(HCPChunk(
            content=raw.content,
            context_prefix=context_prefix,
            section_path=section_path,
            similarity_score=similarity,
            context_levels_included=levels,
            start_line=raw.start_line,
            end_line=raw.end_line,
            chunk_index=i + 1,
            total_chunks=total,
            role=role,
            preceding_excerpt=preceding,
            following_excerpt=following,
        ))

    return chunks


def chunk_document(markdown_text: str, index: StructuralIndex,
                   max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS) -> list[HCPChunk]:
    """Backward-compatible alias for chunk_with_context()."""
    return chunk_with_context(markdown_text, index, max_chunk_tokens)


# ---------------------------------------------------------------------------
# Quality gate — verifies prepends were generated. FAILS OPEN.
# ---------------------------------------------------------------------------

def verify_prepends(chunks: list[HCPChunk], index: StructuralIndex,
                    source_text: str | None = None) -> HCPQualityReport:
    """
    Verify that HCP context prepends were correctly generated before the
    document is marked processed.

    Checks: every chunk carries the Level 1-2 floor; full-depth interior
    chunks carry real Level 5 continuity; the chunk set covers the source
    document's substantive lines without loss.

    Per the standing no-stop-gates rule this gate FAILS OPEN: a failed
    check is an issue on the report (and logged loudly by callers such as
    process_long_form), never a block.
    """
    issues: list[str] = []
    histogram: dict[int, int] = {}

    if not chunks and source_text is not None:
        if _non_heading_lines(source_text.split('\n')):
            issues.append("no chunks were produced for a non-empty document")

    for chunk in chunks:
        histogram[chunk.context_levels_included] = \
            histogram.get(chunk.context_levels_included, 0) + 1
        label = f"chunk {chunk.chunk_index}/{chunk.total_chunks} ({chunk.section_path})"
        if not chunk.context_prefix.strip():
            issues.append(f"{label}: empty context prefix")
            continue
        if "[POSITION]" not in chunk.context_prefix:
            issues.append(f"{label}: missing Level 1 breadcrumb")
        if index.document_thesis and "[THESIS]" not in chunk.context_prefix:
            issues.append(f"{label}: missing Level 2 thesis")
        if chunk.context_levels_included < 2:
            issues.append(f"{label}: below the Level 1-2 floor")
        if chunk.context_levels_included >= 5:
            if chunk.chunk_index > 1 and not chunk.preceding_excerpt:
                issues.append(f"{label}: full-depth chunk missing preceding continuity")
            if chunk.chunk_index < chunk.total_chunks and not chunk.following_excerpt:
                issues.append(f"{label}: full-depth chunk missing following continuity")

    if source_text is not None and chunks:
        all_content = "\n".join(c.content for c in chunks)
        src_lines = source_text.split('\n')
        fence = _fence_mask(src_lines)
        missing = 0
        for i, line in enumerate(src_lines):
            stripped = line.strip()
            if not stripped or len(stripped) <= 2:
                continue
            # A genuine (non-fenced) heading travels via breadcrumb, not
            # literal body text, so it isn't audited here. A fenced line
            # that merely LOOKS heading-shaped (e.g. a '# comment' at
            # column 0 inside a code fence) is real content and IS
            # audited — fence state overrides heading shape, matching
            # _non_heading_lines.
            if not fence[i] and _is_heading(line):
                continue
            if line.rstrip() not in all_content and stripped not in all_content:
                missing += 1
        if missing:
            issues.append(
                f"coverage loss: {missing} substantive source line(s) absent "
                f"from the chunk set")

    return HCPQualityReport(
        ok=not issues,
        issues=issues,
        chunk_count=len(chunks),
        levels_histogram=histogram,
    )


def _log_gate_failure(report: HCPQualityReport, doc_title: str = ""):
    """Loud, fail-open logging for a failed quality gate."""
    banner = "=" * 62
    print(banner, file=sys.stderr)
    print(f"HCP QUALITY GATE FAILED{f' — {doc_title}' if doc_title else ''}: "
          f"{len(report.issues)} issue(s). FAILING OPEN — all chunks are "
          f"returned and nothing is blocked; review the issues below.",
          file=sys.stderr)
    for issue in report.issues[:25]:
        print(f"  - {issue}", file=sys.stderr)
    if len(report.issues) > 25:
        print(f"  … and {len(report.issues) - 25} more", file=sys.stderr)
    print(banner, file=sys.stderr)


# ---------------------------------------------------------------------------
# Convenience: full HCP processing pipeline
# ---------------------------------------------------------------------------

def process_long_form(markdown_text: str, call_fn=None, endpoint=None,
                      max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
                      similarity_fn=None) -> list[HCPChunk]:
    """
    Full HCP processing: Pass 1 (structural index) + Pass 2 (chunk with
    context) + quality gate.

    Returns ALL chunks — low-similarity chunks carry the compressed
    breadcrumb+thesis prepend instead of being dropped. A failed quality
    gate logs loudly to stderr and FAILS OPEN (chunks are still returned);
    call verify_prepends() directly if you need the report itself.
    """
    index = build_structural_index(markdown_text, call_fn, endpoint)
    chunks = chunk_with_context(markdown_text, index, max_chunk_tokens,
                                similarity_fn=similarity_fn)

    report = verify_prepends(chunks, index, markdown_text)
    if not report.ok:
        _log_gate_failure(report, index.document_title)

    return chunks


def format_chunk_for_extraction(chunk: HCPChunk) -> str:
    """
    Format a chunk with its HCP context prefix for feeding into the extraction engine.
    """
    if chunk.context_prefix:
        return f"{chunk.context_prefix}\n\n---\n\n{chunk.content}"
    return chunk.content


class HCPProcessor:
    """Convenience wrapper over the two-pass pipeline — the class the module
    docstring documents.

    Usage:
        processor = HCPProcessor()
        index = processor.build_structural_index(markdown_text)
        chunks = processor.chunk_with_context(markdown_text, index)
        # or:
        chunks = processor.process(markdown_text)
    """

    def __init__(self, call_fn=None, endpoint=None,
                 max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
                 similarity_fn=None):
        self.call_fn = call_fn
        self.endpoint = endpoint
        self.max_chunk_tokens = max_chunk_tokens
        self.similarity_fn = similarity_fn

    def build_structural_index(self, markdown_text: str) -> StructuralIndex:
        return build_structural_index(markdown_text, self.call_fn, self.endpoint)

    def chunk_with_context(self, markdown_text: str,
                           index: StructuralIndex | None = None) -> list[HCPChunk]:
        if index is None:
            index = self.build_structural_index(markdown_text)
        return chunk_with_context(markdown_text, index, self.max_chunk_tokens,
                                  similarity_fn=self.similarity_fn)

    def process(self, markdown_text: str) -> list[HCPChunk]:
        return process_long_form(markdown_text, self.call_fn, self.endpoint,
                                 self.max_chunk_tokens,
                                 similarity_fn=self.similarity_fn)

    def verify(self, chunks: list[HCPChunk], index: StructuralIndex,
               markdown_text: str | None = None) -> HCPQualityReport:
        return verify_prepends(chunks, index, markdown_text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: hcp.py <file_path>")
        print("  Builds structural index and chunks a long-form document.")
        sys.exit(1)

    file_path = sys.argv[1]

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    index = build_structural_index(text)

    print(f"Document: {index.document_title}")
    print(f"Thesis: {index.document_thesis}")
    print(f"Sections: {index.total_sections}")
    print(f"Estimated tokens: {index.estimated_tokens}")
    print()

    if index.sections:
        print("Structure:")
        for s in index.sections[:20]:
            indent = "  " * (s.level - 1)
            print(f"  {indent}{'#' * s.level} {s.title}")
            if s.argument:
                print(f"  {indent}  → {s.argument[:80]}...")
        if len(index.sections) > 20:
            print(f"  ... and {len(index.sections) - 20} more sections")

    print()
    chunks = chunk_with_context(text, index)
    report = verify_prepends(chunks, index, text)
    print(f"Chunks: {len(chunks)}  (quality gate: {'ok' if report.ok else 'FAILED — see stderr'})")
    if not report.ok:
        _log_gate_failure(report, index.document_title)
    for chunk in chunks[:5]:
        print(f"  Chunk {chunk.chunk_index}/{chunk.total_chunks}: {chunk.section_path}")
        print(f"    Similarity: {chunk.similarity_score:.2f}, Context levels: {chunk.context_levels_included}")
        print(f"    Content preview: {chunk.content[:80]}...")
    if len(chunks) > 5:
        print(f"  ... and {len(chunks) - 5} more chunks")
