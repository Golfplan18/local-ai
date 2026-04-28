"""
hcp.py — Hierarchical Context Protocol for Long-Form Document Processing (Phase 10, Step 8)

When processing long-form sources (books, papers, reports), HCP provides
six context levels prepended to each chunk before extraction. This preserves
the document's structural context even when processing chunks independently.

Six context levels:
  1. Positional breadcrumb — where the chunk sits in the document
  2. Source-level thesis — the document's overall argument
  3. Part/section argument — the argument of the containing section
  4. Chapter-level claim — the specific claim of the containing chapter
  5. Local narrative continuity — what the preceding section established
  6. Role declaration — processing context

Similarity-scaling rules:
  >= 0.90 — all six levels
  0.75-0.89 — levels 1-4
  0.60-0.74 — levels 1-2
  < 0.60 — exclude chunk

Usage:
    from orchestrator.tools.hcp import HCPProcessor
    processor = HCPProcessor()
    index = processor.build_structural_index(markdown_text)
    chunks = processor.chunk_with_context(markdown_text, index)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Section:
    """A section in the document hierarchy."""
    level: int          # heading level (1-6)
    title: str          # heading text
    start_line: int     # line index in source
    end_line: int       # line index of section end
    argument: str = ""  # one-sentence summary (populated during indexing)
    parent_idx: int | None = None  # index into sections list


@dataclass
class StructuralIndex:
    """The structural index of a document."""
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


# ---------------------------------------------------------------------------
# Structural index builder
# ---------------------------------------------------------------------------

def build_structural_index(markdown_text: str, call_fn=None, endpoint=None) -> StructuralIndex:
    """
    Build a structural index of a long-form document.

    The index identifies the document's hierarchical structure, extracts
    section arguments, and estimates the thesis.

    Args:
        markdown_text: The full document in markdown format.
        call_fn: Optional model call function for thesis/argument extraction.
                 If None, uses heuristic extraction.
        endpoint: Model endpoint for call_fn.

    Returns:
        StructuralIndex with sections and arguments populated.
    """
    lines = markdown_text.split('\n')
    sections = []

    # Parse heading structure
    for i, line in enumerate(lines):
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

    # Set end_line for each section (starts at next section of same or higher level)
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

    # Estimate tokens
    estimated_tokens = len(markdown_text) // 4

    # Extract arguments for each section
    if call_fn and endpoint:
        # Use model for argument extraction
        _extract_arguments_with_model(sections, lines, call_fn, endpoint)
    else:
        # Heuristic: use first paragraph of each section as argument
        _extract_arguments_heuristic(sections, lines)

    # Extract thesis (first section's argument or document-level summary)
    thesis = ""
    for s in sections:
        if s.level <= 2 and s.argument:
            thesis = s.argument
            break
    if not thesis:
        # Fallback: use first substantive paragraph
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
        # Get content between this heading and the next heading or section end
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
            # Truncate to ~200 chars
            if len(argument) > 200:
                argument = argument[:197] + "..."
            section.argument = argument


def _extract_arguments_with_model(sections: list[Section], lines: list[str],
                                   call_fn, endpoint):
    """Use a model to extract section arguments (one-sentence summaries)."""
    # Build a summary of section headings and first paragraphs
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

    response = call_fn(messages, endpoint)
    if response:
        # Parse numbered lines
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
# Chunking with HCP context
# ---------------------------------------------------------------------------

def chunk_document(markdown_text: str, index: StructuralIndex,
                   max_chunk_tokens: int = 2000) -> list[HCPChunk]:
    """
    Chunk a long-form document with HCP context levels.

    Chunks are created at natural section boundaries. Each chunk gets
    contextual levels prepended based on its position in the hierarchy.

    Args:
        markdown_text: The full document markdown.
        index: The structural index from build_structural_index().
        max_chunk_tokens: Maximum tokens per chunk (approximate).

    Returns:
        List of HCPChunk objects with context prepended.
    """
    lines = markdown_text.split('\n')
    chunks = []

    # Use sections as natural chunk boundaries
    # For sections smaller than max_chunk_tokens, merge with adjacent sections
    # For sections larger than max_chunk_tokens, split at paragraph boundaries

    for section in index.sections:
        section_lines = lines[section.start_line:section.end_line]
        section_text = '\n'.join(section_lines)
        section_tokens = len(section_text) // 4

        if section_tokens <= max_chunk_tokens:
            # Section fits in one chunk
            chunks.append(_create_hcp_chunk(
                content=section_text,
                section=section,
                index=index,
                start_line=section.start_line,
                end_line=section.end_line,
            ))
        else:
            # Split section at paragraph boundaries
            paragraphs = _split_into_paragraphs(section_lines)
            current_para_lines = []
            current_start = section.start_line

            for para_lines in paragraphs:
                para_tokens = sum(len(l) for l in para_lines) // 4
                current_tokens = sum(len(l) for l in current_para_lines) // 4

                if current_tokens + para_tokens > max_chunk_tokens and current_para_lines:
                    # Emit current chunk
                    chunk_text = '\n'.join(current_para_lines)
                    chunks.append(_create_hcp_chunk(
                        content=chunk_text,
                        section=section,
                        index=index,
                        start_line=current_start,
                        end_line=current_start + len(current_para_lines),
                    ))
                    current_para_lines = []
                    current_start = current_start + len(current_para_lines)

                current_para_lines.extend(para_lines)

            # Emit remaining
            if current_para_lines:
                chunk_text = '\n'.join(current_para_lines)
                chunks.append(_create_hcp_chunk(
                    content=chunk_text,
                    section=section,
                    index=index,
                    start_line=current_start,
                    end_line=section.end_line,
                ))

    return chunks


def _create_hcp_chunk(content: str, section: Section, index: StructuralIndex,
                      start_line: int, end_line: int) -> HCPChunk:
    """Create an HCPChunk with context levels."""
    # Build breadcrumb path
    path_parts = [section.title]
    current = section
    while current.parent_idx is not None:
        parent = index.sections[current.parent_idx]
        path_parts.insert(0, parent.title)
        current = parent
    section_path = " > ".join(path_parts)

    # Calculate similarity (placeholder — in production, use embedding similarity)
    # For now, estimate based on structural position and argument overlap
    similarity = _estimate_similarity(content, index.document_thesis)

    # Determine how many context levels to include
    if similarity >= 0.90:
        levels = 6
    elif similarity >= 0.75:
        levels = 4
    elif similarity >= 0.60:
        levels = 2
    else:
        levels = 0  # chunk should be excluded

    # Build context prefix
    context_prefix = _build_context_prefix(
        section=section,
        index=index,
        section_path=section_path,
        levels=levels,
    )

    return HCPChunk(
        content=content,
        context_prefix=context_prefix,
        section_path=section_path,
        similarity_score=similarity,
        context_levels_included=levels,
        start_line=start_line,
        end_line=end_line,
    )


def _build_context_prefix(section: Section, index: StructuralIndex,
                           section_path: str, levels: int) -> str:
    """Build the HCP context prefix for a chunk."""
    if levels == 0:
        return ""

    parts = []

    # Level 1 — Positional breadcrumb
    if levels >= 1:
        parts.append(f"[POSITION] {section_path}")

    # Level 2 — Source-level thesis
    if levels >= 2:
        parts.append(f"[THESIS] {index.document_thesis}")

    # Level 3 — Part/section argument
    if levels >= 3:
        # Find the nearest ancestor with an argument
        if section.parent_idx is not None:
            parent = index.sections[section.parent_idx]
            if parent.argument:
                parts.append(f"[SECTION] {parent.title}: {parent.argument}")

    # Level 4 — Chapter-level claim
    if levels >= 4:
        if section.argument:
            parts.append(f"[CHAPTER] {section.title}: {section.argument}")

    # Level 5 — Local narrative continuity
    if levels >= 5:
        # Find the preceding section at the same level
        section_idx = None
        for i, s in enumerate(index.sections):
            if s.start_line == section.start_line:
                section_idx = i
                break
        if section_idx and section_idx > 0:
            prev = index.sections[section_idx - 1]
            if prev.argument:
                parts.append(f"[PRECEDING] {prev.title}: {prev.argument}")

    # Level 6 — Role declaration
    if levels >= 6:
        parts.append(
            f"[ROLE] You are extracting knowledge from '{index.document_title}'. "
            f"The following chunk is from: {section_path}"
        )

    return "\n".join(parts)


def _estimate_similarity(chunk_text: str, thesis: str) -> float:
    """
    Estimate semantic similarity between chunk and document thesis.

    This is a heuristic fallback. In production, use embedding cosine similarity.
    The heuristic counts keyword overlap between chunk and thesis.
    """
    if not thesis:
        return 0.80  # default — include with partial context

    # Tokenize both
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
    chunk_tokens = tokenize(chunk_text[:1000])  # limit chunk scan

    if not thesis_tokens:
        return 0.80

    overlap = thesis_tokens & chunk_tokens
    score = len(overlap) / len(thesis_tokens)

    # Scale to 0.5-1.0 range (pure keyword overlap rarely exceeds 0.5)
    return min(1.0, 0.5 + score)


def _split_into_paragraphs(lines: list[str]) -> list[list[str]]:
    """Split lines into paragraph groups (separated by blank lines)."""
    paragraphs = []
    current = []

    for line in lines:
        if not line.strip():
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)

    if current:
        paragraphs.append(current)

    return paragraphs


# ---------------------------------------------------------------------------
# Convenience: full HCP processing pipeline
# ---------------------------------------------------------------------------

def process_long_form(markdown_text: str, call_fn=None, endpoint=None,
                      max_chunk_tokens: int = 2000) -> list[HCPChunk]:
    """
    Full HCP processing: build index + chunk with context.

    Args:
        markdown_text: The document to process.
        call_fn: Optional model call function for better argument extraction.
        endpoint: Model endpoint for call_fn.
        max_chunk_tokens: Maximum tokens per chunk.

    Returns:
        List of HCPChunk objects. Chunks with similarity < 0.60 are excluded.
    """
    index = build_structural_index(markdown_text, call_fn, endpoint)
    chunks = chunk_document(markdown_text, index, max_chunk_tokens)

    # Filter out chunks below similarity threshold
    filtered = [c for c in chunks if c.similarity_score >= 0.60]

    return filtered


def format_chunk_for_extraction(chunk: HCPChunk) -> str:
    """
    Format a chunk with its HCP context prefix for feeding into the extraction engine.
    """
    if chunk.context_prefix:
        return f"{chunk.context_prefix}\n\n---\n\n{chunk.content}"
    return chunk.content


if __name__ == "__main__":
    import sys

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
    chunks = chunk_document(text, index)
    print(f"Chunks: {len(chunks)}")
    for i, chunk in enumerate(chunks[:5], 1):
        print(f"  Chunk {i}: {chunk.section_path}")
        print(f"    Similarity: {chunk.similarity_score:.2f}, Context levels: {chunk.context_levels_included}")
        print(f"    Content preview: {chunk.content[:80]}...")
    if len(chunks) > 5:
        print(f"  ... and {len(chunks) - 5} more chunks")
