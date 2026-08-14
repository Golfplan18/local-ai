"""Phase C must add relationships without rewriting the rest of the frontmatter.

``write_note_with_relationships`` once parsed a note's frontmatter and re-emitted
it with ``yaml.safe_dump``. That silently rewrote every note it touched even
where no value changed: a bare ``nexus:`` became ``nexus: null``, ``processed_at``
lost its ISO ``T`` separator, long scalars were re-wrapped, and list indentation
shifted. It also contradicted ``apply_rewrites.py``, which keeps frontmatter
verbatim by design, so the corpus would have ended up normalized or not
depending on which pass last touched each note.

These tests pin the byte-preservation property. Fixtures are synthetic on
purpose — an earlier version of this test copied a live corpus note and started
failing when a background run modified it underneath.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from orchestrator.historical.phase_c_relationship_extraction import (
    write_note_with_relationships,
)

NOTE_NO_RELS = """\
---
nexus:
type: engram
tags:
  - atomic
  - definition
date created: 2023-12-20
date modified: 2026-07-13
source_chat: ~/Documents/conversations/raw/Raw Chats 2025-1-12/A Long Source Name Here.md
source_pair_num: 34
processed_at: 2026-07-13T12:02:36
seen_count: 1
---

# A claim that states something worth knowing

- A bullet carrying the mechanism.
- Another bullet, with a trailing newline after it.
"""

RELS = [
    {"type": "supports", "target": "Short target with no punctuation",
     "confidence": "high"},
    {"type": "analogous-to",
     "target": ("A very long claim sentence that certainly exceeds ninety "
                "characters and contains: a colon, plus \"quotes\", so it "
                "must fold"),
     "confidence": "medium"},
]


def _frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter without fences, body) — mirrors the module's own regex."""
    assert text.startswith("---\n")
    end = text.index("\n---\n", 3)
    return text[4:end], text[end + 5:]


class TestFrontmatterSplice(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _note(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_body_and_frontmatter_preserved_byte_for_byte(self):
        p = self._note("a.md", NOTE_NO_RELS)
        fm_before, body_before = _frontmatter(p.read_text())

        write_note_with_relationships(p, RELS)

        fm_after, body_after = _frontmatter(p.read_text())
        self.assertEqual(body_before, body_after, "body must be untouched")
        self.assertTrue(
            fm_after.startswith(fm_before),
            "existing frontmatter must survive as an exact prefix",
        )
        added = fm_after[len(fm_before):].lstrip("\n")
        self.assertTrue(added.startswith("relationships:"),
                        f"only a relationships block may be added, got {added[:60]!r}")

    def test_no_yaml_renormalization(self):
        """The specific regressions safe_dump introduced."""
        p = self._note("b.md", NOTE_NO_RELS)
        write_note_with_relationships(p, RELS)
        fm, _ = _frontmatter(p.read_text())

        self.assertIn("nexus:\n", fm, "bare nexus: must not become nexus: null")
        self.assertNotIn("nexus: null", fm)
        self.assertIn("processed_at: 2026-07-13T12:02:36", fm,
                      "ISO T separator must survive")
        self.assertIn("  - atomic", fm, "list indentation must survive")
        self.assertIn(
            "source_chat: ~/Documents/conversations/raw/Raw Chats 2025-1-12/"
            "A Long Source Name Here.md",
            fm,
            "long scalars must not be re-wrapped",
        )

    def test_relationships_round_trip_through_yaml(self):
        p = self._note("c.md", NOTE_NO_RELS)
        write_note_with_relationships(p, RELS)
        fm, _ = _frontmatter(p.read_text())

        parsed = yaml.safe_load(fm)
        self.assertEqual(parsed["relationships"], RELS,
                         "folded block scalars must round-trip exactly")

    def test_empty_relationships_leaves_file_untouched(self):
        p = self._note("d.md", NOTE_NO_RELS)
        before = p.read_bytes()

        write_note_with_relationships(p, [])

        self.assertEqual(p.read_bytes(), before,
                         "a note with no links found must not gain an empty property")

    def test_rerun_replaces_rather_than_duplicates(self):
        p = self._note("e.md", NOTE_NO_RELS)
        write_note_with_relationships(p, RELS)
        first = p.read_bytes()

        write_note_with_relationships(p, RELS)

        self.assertEqual(p.read_bytes(), first, "the write must be idempotent")
        fm, _ = _frontmatter(p.read_text())
        self.assertEqual(fm.count("relationships:"), 1)

    def test_existing_block_replaced_without_touching_other_keys(self):
        p = self._note("f.md", NOTE_NO_RELS)
        write_note_with_relationships(p, RELS)
        fm_first, body_first = _frontmatter(p.read_text())
        non_rel = fm_first.split("\nrelationships:")[0]

        replacement = [{"type": "extends", "target": "A different target",
                        "confidence": "low"}]
        write_note_with_relationships(p, replacement)

        fm_after, body_after = _frontmatter(p.read_text())
        self.assertEqual(body_first, body_after)
        self.assertEqual(fm_after.split("\nrelationships:")[0], non_rel,
                         "non-relationship keys must be untouched by a replace")
        self.assertEqual(yaml.safe_load(fm_after)["relationships"], replacement)
        self.assertEqual(fm_after.count("relationships:"), 1)

    def test_missing_frontmatter_raises_rather_than_writing(self):
        p = self._note("g.md", "# No frontmatter here\n\n- a bullet\n")
        before = p.read_bytes()

        with self.assertRaises(ValueError):
            write_note_with_relationships(p, RELS)

        self.assertEqual(p.read_bytes(), before, "a failed write must not mutate")


if __name__ == "__main__":
    unittest.main()
