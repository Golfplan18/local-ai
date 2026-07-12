"""Tests for orchestrator/tools/hcp.py — Hierarchical Context Protocol.

Canonical spec: vault "Specification — Hierarchical Context Protocol.md"
(from the recovered 2026-04-11 dictation). The load-bearing behaviors:

  - Two-pass ingestion: Pass 1 builds the structural index; Pass 2 cuts
    chunks and injects context, so Level 5 continuity can quote the ACTUAL
    adjacent chunks.
  - Six context levels, similarity-scaled prepend depth.
  - NO chunk is ever dropped — low similarity compresses the prepend to
    the breadcrumb+thesis floor (the old skeleton silently discarded
    chunks below 0.60).
  - Quality gate verifies prepends and FAILS OPEN (loud log, no block).
  - HCPProcessor exists and works as the module docstring documents
    (the old docstring advertised a class that didn't exist).
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.tools import hcp  # noqa: E402

# Deterministic embedding stub so the default similarity scorer never
# depends on a running Ollama instance.
from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


DOC = """# The Adversarial AI Agent

Natural language is source code and domain expertise is the irreplaceable ingredient.

## Part Two: The Architecture

The architecture part argues that adversarial pipelines beat single-model flows.

### Chapter 8: The Adversarial Pipeline

This chapter claims the adversarial pipeline is the correct architecture for reliability.

#### Parallel Independent Analysis

Parallel analysis runs several models at once. Independent runs prevent anchoring on a single model's framing. This paragraph establishes the mechanism.

The evidence paragraph follows here. A benchmark study measured error rates dropping under parallel review. The data supports independent analysis over sequential critique.

Therefore the adversarial pipeline is the correct architecture. That conclusion rests on the mechanism and the measurements above.
"""

FULL = lambda _text: 1.0   # noqa: E731 — force all six levels
LOW = lambda _text: 0.10   # noqa: E731 — force the compressed floor


class TestPassOneStructuralIndex(unittest.TestCase):

    def test_hierarchy_and_arguments(self):
        index = hcp.build_structural_index(DOC)
        self.assertEqual(index.document_title, "The Adversarial AI Agent")
        self.assertEqual(index.total_sections, 4)
        self.assertIn("Natural language is source code", index.document_thesis)
        # Parent chain: H4 -> H3 -> H2 -> H1
        h4 = index.sections[3]
        self.assertEqual(h4.title, "Parallel Independent Analysis")
        h3 = index.sections[h4.parent_idx]
        self.assertEqual(h3.title, "Chapter 8: The Adversarial Pipeline")
        h2 = index.sections[h3.parent_idx]
        self.assertEqual(h2.title, "Part Two: The Architecture")
        # Heuristic one-sentence arguments populated at every level.
        for s in index.sections:
            self.assertTrue(s.argument, f"section '{s.title}' has no argument")


class TestPassTwoChunking(unittest.TestCase):

    def test_breadcrumb_uses_pass_one_hierarchy(self):
        # Two-pass correctness: the chunk in the deepest section carries the
        # full breadcrumb path derived from the Pass 1 structural index.
        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        deep = [c for c in chunks
                if c.section_path.endswith("Parallel Independent Analysis")]
        self.assertTrue(deep)
        self.assertEqual(
            deep[0].section_path,
            "The Adversarial AI Agent > Part Two: The Architecture > "
            "Chapter 8: The Adversarial Pipeline > Parallel Independent Analysis")
        self.assertIn("[POSITION] The Adversarial AI Agent >",
                      deep[0].context_prefix)

    def test_chunk_index_totals(self):
        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        self.assertGreater(len(chunks), 1)
        for i, c in enumerate(chunks, 1):
            self.assertEqual(c.chunk_index, i)
            self.assertEqual(c.total_chunks, len(chunks))

    def test_no_duplicated_content_across_nested_sections(self):
        # Regions must be leaf regions: parent sections must not re-chunk
        # their children's text.
        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        blob = "\n\n".join(c.content for c in chunks)
        sentinel = "Independent runs prevent anchoring"
        self.assertEqual(blob.count(sentinel), 1)

    def test_preamble_before_first_heading_is_kept(self):
        doc = "An opening paragraph before any heading.\n\n# Title\n\nBody text here.\n"
        index = hcp.build_structural_index(doc)
        chunks = hcp.chunk_with_context(doc, index, similarity_fn=FULL)
        blob = "\n".join(c.content for c in chunks)
        self.assertIn("An opening paragraph before any heading.", blob)

    def test_headingless_document_is_kept(self):
        doc = ("No headings anywhere in this document.\n\n"
               "Just two paragraphs of plain prose that must survive chunking.\n")
        index = hcp.build_structural_index(doc)
        chunks = hcp.chunk_with_context(doc, index, similarity_fn=FULL)
        self.assertTrue(chunks)
        blob = "\n".join(c.content for c in chunks)
        self.assertIn("No headings anywhere", blob)
        self.assertIn("must survive chunking", blob)

    def test_oversized_section_splits_at_paragraphs_without_loss(self):
        paras = [f"Paragraph number {i}. " + ("Filler sentence text. " * 12)
                 for i in range(12)]
        doc = "# Big Section\n\n" + "\n\n".join(paras) + "\n"
        index = hcp.build_structural_index(doc)
        chunks = hcp.chunk_with_context(doc, index, max_chunk_tokens=100,
                                        similarity_fn=FULL)
        self.assertGreater(len(chunks), 1)
        blob = "\n\n".join(c.content for c in chunks)
        for i in range(12):
            self.assertIn(f"Paragraph number {i}.", blob)
        # Quality gate agrees there is no coverage loss.
        report = hcp.verify_prepends(chunks, index, doc)
        self.assertTrue(report.ok, report.issues)


class TestLevelFiveContinuity(unittest.TestCase):
    """Level 5 quotes the ACTUAL adjacent chunks — the reason ingestion is
    two-pass."""

    def setUp(self):
        self.index = hcp.build_structural_index(DOC)
        self.chunks = hcp.chunk_with_context(DOC, self.index, similarity_fn=FULL)
        self.assertGreaterEqual(len(self.chunks), 3)

    def test_interior_chunk_quotes_real_neighbors(self):
        mid = self.chunks[1]
        prev, nxt = self.chunks[0], self.chunks[2]
        self.assertEqual(mid.preceding_excerpt,
                         hcp._closing_sentences(prev.content))
        self.assertEqual(mid.following_excerpt,
                         hcp._opening_sentences(nxt.content))
        self.assertIn(f"[PRECEDING] …{mid.preceding_excerpt}", mid.context_prefix)
        self.assertIn(f"[FOLLOWING] {mid.following_excerpt}…", mid.context_prefix)
        # The excerpt is text that genuinely occurs in the neighbor chunks.
        self.assertIn(mid.preceding_excerpt.split(". ")[-1].rstrip("."),
                      prev.content)

    def test_boundary_chunks_have_one_sided_continuity(self):
        first, last = self.chunks[0], self.chunks[-1]
        self.assertEqual(first.preceding_excerpt, "")
        self.assertNotIn("[PRECEDING]", first.context_prefix)
        self.assertTrue(first.following_excerpt)
        self.assertEqual(last.following_excerpt, "")
        self.assertNotIn("[FOLLOWING]", last.context_prefix)
        self.assertTrue(last.preceding_excerpt)


class TestSimilarityScalingAndNoDrop(unittest.TestCase):

    def test_full_similarity_gets_all_six_levels(self):
        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        deep = [c for c in chunks
                if c.section_path.endswith("Parallel Independent Analysis")][0]
        self.assertEqual(deep.context_levels_included, 6)
        for tag in ("[POSITION]", "[THESIS]", "[CONTEXT]", "[SECTION]", "[ROLE]"):
            self.assertIn(tag, deep.context_prefix)

    def test_low_similarity_compresses_but_never_drops(self):
        # The old skeleton PERMANENTLY DROPPED chunks under 0.60. Spec:
        # keep them retrievable with the breadcrumb+thesis floor.
        index = hcp.build_structural_index(DOC)
        full = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        low = hcp.chunk_with_context(DOC, index, similarity_fn=LOW)
        self.assertEqual(len(low), len(full))  # nothing dropped
        for c in low:
            self.assertEqual(c.context_levels_included, 2)
            self.assertIn("[POSITION]", c.context_prefix)
            self.assertIn("[THESIS]", c.context_prefix)
            for tag in ("[CONTEXT]", "[SECTION]", "[PRECEDING]",
                        "[FOLLOWING]", "[ROLE]"):
                self.assertNotIn(tag, c.context_prefix)

    def test_process_long_form_returns_everything_at_low_similarity(self):
        chunks = hcp.process_long_form(DOC, similarity_fn=LOW)
        self.assertGreater(len(chunks), 0)
        blob = "\n".join(c.content for c in chunks)
        self.assertIn("Therefore the adversarial pipeline", blob)


class TestRoleDeclaration(unittest.TestCase):

    def test_marker_classification(self):
        self.assertEqual(
            hcp._declare_role("Therefore it holds. Thus, we conclude. "
                              "In conclusion the case is made.", False),
            "states a conclusion")
        self.assertEqual(
            hcp._declare_role("For example, a study measured this. "
                              "The data shows the effect. More evidence follows.",
                              False),
            "provides evidence")
        self.assertEqual(
            hcp._declare_role("However, critics raise an objection here.", False),
            "introduces a counterargument")
        self.assertEqual(hcp._declare_role("Plain descriptive text.", True),
                         "establishes a premise")
        self.assertEqual(hcp._declare_role("Plain descriptive text.", False),
                         "develops the section's argument")

    def test_role_travels_at_full_depth(self):
        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)
        for c in chunks:
            self.assertIn("[ROLE] This chunk", c.context_prefix)
            self.assertTrue(c.role)


class TestQualityGate(unittest.TestCase):

    def setUp(self):
        self.index = hcp.build_structural_index(DOC)
        self.chunks = hcp.chunk_with_context(DOC, self.index, similarity_fn=FULL)

    def test_gate_passes_on_good_output(self):
        report = hcp.verify_prepends(self.chunks, self.index, DOC)
        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.chunk_count, len(self.chunks))
        self.assertIn(6, report.levels_histogram)

    def test_gate_flags_missing_prepend(self):
        self.chunks[1].context_prefix = ""
        report = hcp.verify_prepends(self.chunks, self.index, DOC)
        self.assertFalse(report.ok)
        self.assertTrue(any("empty context prefix" in i for i in report.issues))

    def test_gate_flags_coverage_loss(self):
        report = hcp.verify_prepends(self.chunks[:-1], self.index, DOC)
        self.assertFalse(report.ok)
        self.assertTrue(any("coverage loss" in i for i in report.issues))

    def test_gate_fails_open(self):
        # A document that trips the gate still returns all chunks from
        # process_long_form — loud logging, no block.
        chunks = hcp.process_long_form(DOC, similarity_fn=FULL)
        self.assertEqual(len(chunks), len(self.chunks))


class TestHCPProcessorClass(unittest.TestCase):
    """The module docstring's documented usage must actually work (the old
    docstring advertised HCPProcessor while only functions existed)."""

    def test_docstring_usage(self):
        from orchestrator.tools.hcp import HCPProcessor
        processor = HCPProcessor(similarity_fn=FULL)
        index = processor.build_structural_index(DOC)
        chunks = processor.chunk_with_context(DOC, index)
        self.assertTrue(chunks)
        self.assertEqual(chunks[0].total_chunks, len(chunks))
        # One-call form and the gate accessor.
        processed = processor.process(DOC)
        self.assertEqual(len(processed), len(chunks))
        report = processor.verify(processed, index, DOC)
        self.assertTrue(report.ok, report.issues)


class TestFormatForExtraction(unittest.TestCase):

    def test_prefix_precedes_content(self):
        index = hcp.build_structural_index(DOC)
        chunk = hcp.chunk_with_context(DOC, index, similarity_fn=FULL)[0]
        formatted = hcp.format_chunk_for_extraction(chunk)
        self.assertTrue(formatted.startswith(chunk.context_prefix))
        self.assertIn("\n\n---\n\n", formatted)
        self.assertTrue(formatted.endswith(chunk.content))


class TestFencedCodeBlockAwareness(unittest.TestCase):
    """A '#'-prefixed comment line at column 0 inside a fenced code block
    is code, not a markdown heading. Regression coverage for a bug found
    by adversarial review: unguarded heading detection fabricated a
    Section for such a line, splitting the fence mid-block and making the
    fabricated node a false parent of the next real heading."""

    FENCED_DOC = """# Doc Title

## Real Section

Some intro prose.

```python
# this is a comment inside a fenced code block
def foo():
    pass
```

More prose after the code block.

## Next Section

Tail prose that is definitely not a heading.
"""

    def test_fenced_hash_line_is_not_a_section(self):
        index = hcp.build_structural_index(self.FENCED_DOC)
        titles = [s.title for s in index.sections]
        self.assertNotIn("this is a comment inside a fenced code block", titles)
        self.assertEqual(titles, ["Doc Title", "Real Section", "Next Section"])

    def test_fence_is_not_split_and_breadcrumb_is_sane(self):
        index = hcp.build_structural_index(self.FENCED_DOC)
        chunks = hcp.chunk_with_context(self.FENCED_DOC, index, similarity_fn=FULL)
        blob = "\n".join(c.content for c in chunks)
        # The whole fence, including its closing marker and the def body,
        # survives — not split across a fabricated section boundary.
        self.assertIn("def foo():\n    pass\n```", blob)
        # The breadcrumb (Level 1) never routes through the fabricated
        # node — that's what would indicate it became a false parent.
        # (The fenced comment text may legitimately appear in a Level 5
        # continuity excerpt, since it IS real chunk content.)
        for c in chunks:
            position_line = c.context_prefix.split("\n", 1)[0]
            self.assertNotIn("this is a comment inside a fenced code block",
                             position_line)
        next_section = [c for c in chunks
                        if c.section_path.endswith("Next Section")][0]
        self.assertEqual(next_section.section_path, "Doc Title > Next Section")

    def test_gate_reports_no_issues(self):
        index = hcp.build_structural_index(self.FENCED_DOC)
        chunks = hcp.chunk_with_context(self.FENCED_DOC, index, similarity_fn=FULL)
        report = hcp.verify_prepends(chunks, index, self.FENCED_DOC)
        self.assertTrue(report.ok, report.issues)


class TestIndentedHashLinesNotDropped(unittest.TestCase):
    """A section whose only non-blank content is indented lines that start
    with '#' (e.g. an indented YAML/Python comment block with no
    accompanying prose) must not be treated as heading-only and dropped.
    Regression coverage for a bug found by adversarial review: _is_heading
    stripped the line before matching, so indentation was invisible."""

    DOC_WITH_INDENTED_COMMENTS = """# Doc Title

## Config Example

    # config.yaml
    # key: value

## Next Section

Some real prose here that is definitely not a heading.
"""

    def test_indented_hash_section_survives(self):
        index = hcp.build_structural_index(self.DOC_WITH_INDENTED_COMMENTS)
        chunks = hcp.chunk_with_context(self.DOC_WITH_INDENTED_COMMENTS, index,
                                        similarity_fn=FULL)
        blob = "\n".join(c.content for c in chunks)
        self.assertIn("# config.yaml", blob)
        self.assertIn("# key: value", blob)
        section_paths = {c.section_path for c in chunks}
        self.assertTrue(any(p.endswith("Config Example") for p in section_paths))

    def test_gate_reports_no_coverage_loss(self):
        index = hcp.build_structural_index(self.DOC_WITH_INDENTED_COMMENTS)
        chunks = hcp.chunk_with_context(self.DOC_WITH_INDENTED_COMMENTS, index,
                                        similarity_fn=FULL)
        report = hcp.verify_prepends(chunks, index, self.DOC_WITH_INDENTED_COMMENTS)
        self.assertTrue(report.ok, report.issues)


class TestHeadingOnlyChunkNeverEmitted(unittest.TestCase):
    """A section heading immediately followed by a single paragraph that
    alone exceeds max_chunk_tokens must not produce a standalone
    heading-only raw chunk — that emptied the neighboring chunk's Level 5
    continuity excerpt. Regression coverage for a bug found by adversarial
    review."""

    def test_heading_merges_with_oversized_following_paragraph(self):
        doc = "## My Heading\n\n" + ("word " * 2000) + "\n"
        index = hcp.build_structural_index(doc)
        chunks = hcp.chunk_with_context(doc, index, max_chunk_tokens=5,
                                        similarity_fn=FULL)
        # No chunk is heading-only prose.
        for c in chunks:
            self.assertTrue(hcp._prose_text(c.content),
                            f"chunk has no prose: {c.content!r}")
        report = hcp.verify_prepends(chunks, index, doc)
        self.assertTrue(report.ok, report.issues)


class TestSimilarityFnNeverCrashesTheChunker(unittest.TestCase):
    """A raising similarity_fn (custom, or a future broken default) must
    degrade to the compressed floor, not crash the whole call and lose
    every already-cut chunk. Regression coverage for a bug found by
    adversarial review."""

    def test_raising_scorer_still_returns_all_chunks(self):
        def bad_similarity(_text):
            raise RuntimeError("embedder exploded")

        index = hcp.build_structural_index(DOC)
        chunks = hcp.chunk_with_context(DOC, index, similarity_fn=bad_similarity)
        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertEqual(c.context_levels_included, 2)
            self.assertIn("[POSITION]", c.context_prefix)


if __name__ == "__main__":
    unittest.main()
