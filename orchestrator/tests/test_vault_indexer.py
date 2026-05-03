"""Tests for the vault index builder (Phase 0 of historical reprocessing).

The indexer scans the vault for mature artifacts and emits a JSON index
that AI consults during Phase 1 cleanup to spot when pasted material is
just an earlier version of something already in mature form in the vault.

Verifies:
  - Skip rules: .bak files, conversation-chunk filenames, transient subdirs.
  - Maturity classification: top-level mature, working subdirs flagged.
  - YAML frontmatter parser: handles tags, lists, type field.
  - Title extraction: H1 first, filename fallback.
  - Paragraph hashing: significant paragraphs only, stable, normalization.
  - Topic fingerprint: deterministic, stable across minor edits.
  - Build pipeline: full build, incremental update, rebuild flag.
  - Lookup: paragraph-hash overlap, topic-fingerprint match.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.tools.vault_indexer import (  # noqa: E402
    build_entry,
    build_index,
    classify_maturity,
    extract_key_phrases,
    extract_title,
    find_matches_by_paragraph_hash,
    find_matches_by_topic_fingerprint,
    iter_vault_files,
    load_index,
    normalize_paragraph,
    paragraph_hashes,
    parse_frontmatter,
    should_skip,
    topic_fingerprint,
    yaml_skip_by_type,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_vault(tmpdir: str, files: dict) -> Path:
    """Create a fake vault directory with `files` mapping rel_path → text."""
    vault = Path(tmpdir) / "vault"
    vault.mkdir()
    for rel, text in files.items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return vault


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------


class TestSkipRules(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Path(self.tmp) / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skip_bak_files(self):
        path = self.vault / "thing.md.bak.2026-04-30"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_skip_bak_inside_filename(self):
        path = self.vault / "Reference.md.bak"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_skip_chunk_filename(self):
        path = self.vault / "2026-04-15_10-30_some-topic-here.md"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_skip_sessions_subdir(self):
        sub = self.vault / "Sessions"
        sub.mkdir()
        path = sub / "anything.md"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_skip_temp_subdir(self):
        sub = self.vault / "temp"
        sub.mkdir()
        path = sub / "thing.md"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_skip_dotgit_subdir(self):
        sub = self.vault / ".git"
        sub.mkdir()
        path = sub / "config.md"
        path.touch()
        self.assertTrue(should_skip(path, self.vault))

    def test_keep_top_level_md(self):
        path = self.vault / "Reference — Schema.md"
        path.touch()
        self.assertFalse(should_skip(path, self.vault))

    def test_keep_engrams_subdir(self):
        sub = self.vault / "Engrams" / "Book"
        sub.mkdir(parents=True)
        path = sub / "chapter-1.md"
        path.touch()
        self.assertFalse(should_skip(path, self.vault))


# ---------------------------------------------------------------------------
# Maturity classification
# ---------------------------------------------------------------------------


class TestMaturity(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = Path(self.tmp) / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_top_level_is_mature(self):
        p = self.vault / "Framework — X.md"
        p.touch()
        self.assertTrue(classify_maturity(p, self.vault))

    def test_engrams_is_mature(self):
        p = self.vault / "Engrams" / "x.md"
        p.parent.mkdir()
        p.touch()
        self.assertTrue(classify_maturity(p, self.vault))

    def test_lenses_is_mature(self):
        p = self.vault / "Lenses" / "x.md"
        p.parent.mkdir()
        p.touch()
        self.assertTrue(classify_maturity(p, self.vault))

    def test_modes_is_mature(self):
        p = self.vault / "Modes" / "x.md"
        p.parent.mkdir()
        p.touch()
        self.assertTrue(classify_maturity(p, self.vault))

    def test_workshop_is_working(self):
        p = self.vault / "Workshop" / "x.md"
        p.parent.mkdir()
        p.touch()
        self.assertFalse(classify_maturity(p, self.vault))

    def test_old_ai_working_files_is_working(self):
        p = self.vault / "Old AI Working Files" / "x.md"
        p.parent.mkdir()
        p.touch()
        self.assertFalse(classify_maturity(p, self.vault))


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------


class TestFrontmatter(unittest.TestCase):

    def test_no_frontmatter(self):
        text = "# Title\n\nContent here."
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_simple_frontmatter(self):
        text = "---\ntype: working\ndate created: 2026-04-30\n---\n# Title\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["type"], "working")
        self.assertEqual(meta["date created"], "2026-04-30")
        self.assertEqual(body, "# Title\n")

    def test_list_frontmatter(self):
        text = (
            "---\n"
            "tags:\n"
            "  - alpha\n"
            "  - beta\n"
            "  - gamma\n"
            "type: working\n"
            "---\nbody"
        )
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["tags"], ["alpha", "beta", "gamma"])
        self.assertEqual(meta["type"], "working")

    def test_yaml_skip_by_type_chat(self):
        meta = {"type": "chat"}
        self.assertTrue(yaml_skip_by_type(meta))

    def test_yaml_skip_by_type_cleaned_pair(self):
        meta = {"type": "cleaned-pair"}
        self.assertTrue(yaml_skip_by_type(meta))

    def test_yaml_skip_by_type_working(self):
        meta = {"type": "working"}
        self.assertFalse(yaml_skip_by_type(meta))


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


class TestTitle(unittest.TestCase):

    def test_first_h1(self):
        body = "# My Title\n\nbody here\n"
        self.assertEqual(extract_title(body, fallback="x"), "My Title")

    def test_h1_with_em_dash(self):
        body = "# Reference — Ora YAML Schema\n\nbody"
        self.assertEqual(extract_title(body, fallback="x"),
                         "Reference — Ora YAML Schema")

    def test_no_h1_uses_fallback(self):
        body = "body without heading"
        self.assertEqual(extract_title(body, fallback="filename-stem"),
                         "filename-stem")

    def test_h2_does_not_count(self):
        body = "## Section\n\nbody"
        self.assertEqual(extract_title(body, fallback="fb"), "fb")


# ---------------------------------------------------------------------------
# Paragraph hashing
# ---------------------------------------------------------------------------


class TestParagraphHashing(unittest.TestCase):

    def test_normalize_lowercases(self):
        self.assertEqual(normalize_paragraph("Hello World"), "hello world")

    def test_normalize_strips_punctuation(self):
        self.assertEqual(normalize_paragraph("Hello, world!"), "hello world")

    def test_normalize_collapses_whitespace(self):
        self.assertEqual(normalize_paragraph("a  \n\t b"), "a b")

    def test_short_paragraphs_dropped(self):
        body = "short.\n\nalso short.\n"
        self.assertEqual(paragraph_hashes(body), [])

    def test_long_paragraph_hashed(self):
        long_text = "the quick brown fox " * 20  # > 100 chars normalized
        body = f"# Title\n\n{long_text}"
        hashes = paragraph_hashes(body)
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(hashes[0]), 16)

    def test_hash_stable_across_runs(self):
        long_text = "Quantum mechanics is fundamentally a probabilistic theory describing nature at small scales using wavefunctions."
        body = f"\n\n{long_text}\n\n{long_text}"  # 2 identical paragraphs
        h1 = paragraph_hashes(body)
        h2 = paragraph_hashes(body)
        self.assertEqual(h1, h2)
        # Same paragraph repeated should produce identical hashes
        self.assertEqual(h1[0], h1[1])

    def test_hash_invariant_to_minor_punctuation(self):
        a = "The fundamental theorem of calculus relates derivatives and integrals over an interval. It bridges differential and integral calculus."
        b = "The fundamental theorem of calculus relates derivatives and integrals over an interval; it bridges differential and integral calculus."
        ha = paragraph_hashes(a)
        hb = paragraph_hashes(b)
        # Periods vs semicolon: punctuation stripped, so hashes match.
        self.assertEqual(ha, hb)

    def test_distinct_paragraphs_distinct_hashes(self):
        a = "alpha " * 30
        b = "beta " * 30
        body = f"{a}\n\n{b}"
        hashes = paragraph_hashes(body)
        self.assertEqual(len(hashes), 2)
        self.assertNotEqual(hashes[0], hashes[1])


# ---------------------------------------------------------------------------
# Topic fingerprint + key phrases
# ---------------------------------------------------------------------------


class TestKeyPhrases(unittest.TestCase):

    def test_extracts_capitalized_phrases(self):
        title = "Reference Ora YAML Schema"
        body = "The Wisdom Nexus contains Working Frameworks."
        phrases = extract_key_phrases(title, body)
        joined = " | ".join(phrases).lower()
        self.assertIn("ora", joined)
        self.assertIn("schema", joined)

    def test_drops_pure_stopwords(self):
        # "The The" is all stopwords after lowercasing.
        phrases = extract_key_phrases("The And", "The Or")
        for p in phrases:
            self.assertNotEqual(p.lower(), "the and")

    def test_dedupes_case_insensitively(self):
        title = "Ora ora ORA"
        body = ""
        # All variants collapse to one "ora".
        phrases = extract_key_phrases(title, body)
        lowered = [p.lower() for p in phrases]
        self.assertEqual(len(lowered), len(set(lowered)))


class TestTopicFingerprint(unittest.TestCase):

    def test_deterministic(self):
        a = topic_fingerprint(["NLP Outline", "Volume Three"])
        b = topic_fingerprint(["NLP Outline", "Volume Three"])
        self.assertEqual(a, b)

    def test_order_independent(self):
        a = topic_fingerprint(["Alpha", "Beta", "Gamma"])
        b = topic_fingerprint(["Gamma", "Alpha", "Beta"])
        self.assertEqual(a, b)

    def test_case_independent(self):
        a = topic_fingerprint(["Alpha", "Beta"])
        b = topic_fingerprint(["alpha", "BETA"])
        self.assertEqual(a, b)

    def test_dedup(self):
        a = topic_fingerprint(["Alpha", "alpha", "Alpha"])
        b = topic_fingerprint(["Alpha"])
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# build_entry
# ---------------------------------------------------------------------------


class TestBuildEntry(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_builds_minimal_entry(self):
        vault = _make_vault(self.tmp, {
            "Test.md": "# Test\n\nbody " * 30,
        })
        entry = build_entry(vault / "Test.md", vault, "vault-001")
        self.assertEqual(entry.id, "vault-001")
        self.assertEqual(entry.vault_path, "Test.md")
        self.assertEqual(entry.title, "Test")
        self.assertTrue(entry.mature)
        self.assertGreater(entry.file_mtime, 0)

    def test_yaml_tags_extracted(self):
        text = (
            "---\n"
            "type: working\n"
            "tags:\n"
            "  - alpha\n"
            "  - beta\n"
            "---\n"
            "# Title\n\n" + ("paragraph " * 30)
        )
        vault = _make_vault(self.tmp, {"Tagged.md": text})
        entry = build_entry(vault / "Tagged.md", vault, "vault-002")
        self.assertEqual(entry.yaml_tags, ["alpha", "beta"])
        self.assertEqual(entry.yaml_type, "working")


# ---------------------------------------------------------------------------
# Build index end-to-end
# ---------------------------------------------------------------------------


class TestBuildIndex(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = _make_vault(self.tmp, {
            # Top-level mature
            "Framework — Topic A.md": (
                "---\ntype: working\n---\n"
                "# Framework Topic A\n\n"
                + ("Topic A is about Quantum Mechanics and Schrödinger Equations. " * 20)
            ),
            "Reference — Topic B.md": (
                "---\ntype: working\n---\n"
                "# Reference Topic B\n\n"
                + ("Topic B describes Bayesian Inference and Markov Chains. " * 20)
            ),
            # Engrams subdir mature
            "Engrams/Book/Chapter 1.md": (
                "# Chapter 1\n\n"
                + ("Once upon a time in the Wisdom Nexus there were many Sages. " * 20)
            ),
            # Working subdir
            "Workshop/Draft.md": (
                "# Draft\n\n"
                + ("Drafting some Working Framework ideas here. " * 20)
            ),
            # SHOULD BE SKIPPED: chunk filename
            "2026-04-30_12-00_some-conversation.md": "# chunk content\n\n" + ("body " * 50),
            # SHOULD BE SKIPPED: .bak
            "Framework — Topic A.md.bak.2026-04-29": "old content",
            # SHOULD BE SKIPPED: Sessions subdir
            "Sessions/2026-04-30_session.md": "# session\n\n" + ("body " * 50),
            # SHOULD BE SKIPPED: type: chat YAML
            "Chat Pretender.md": (
                "---\ntype: chat\n---\n"
                "# Pretend\n\n" + ("body " * 50)
            ),
        })
        self.output = Path(self.tmp) / "vault-index.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_build_indexes_only_kept_files(self):
        stats = build_index(vault_path=str(self.vault),
                             output_path=str(self.output),
                             rebuild=True)
        # 4 kept: 2 top-level + 1 Engrams + 1 Workshop
        self.assertEqual(stats["new"], 4)
        self.assertEqual(stats["yaml_skipped"], 1)
        index = load_index(str(self.output))
        paths = {e["vault_path"] for e in index["entries"]}
        self.assertIn("Framework — Topic A.md", paths)
        self.assertIn("Reference — Topic B.md", paths)
        self.assertIn("Engrams/Book/Chapter 1.md", paths)
        self.assertIn("Workshop/Draft.md", paths)
        # And NOT these:
        for must_not in (
            "2026-04-30_12-00_some-conversation.md",
            "Framework — Topic A.md.bak.2026-04-29",
            "Sessions/2026-04-30_session.md",
            "Chat Pretender.md",
        ):
            self.assertNotIn(must_not, paths,
                              f"unexpected entry: {must_not}")

    def test_maturity_flag(self):
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        index = load_index(str(self.output))
        by_path = {e["vault_path"]: e for e in index["entries"]}
        self.assertTrue(by_path["Framework — Topic A.md"]["mature"])
        self.assertTrue(by_path["Engrams/Book/Chapter 1.md"]["mature"])
        self.assertFalse(by_path["Workshop/Draft.md"]["mature"])

    def test_incremental_skips_unchanged(self):
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        # Second run with same files → all unchanged.
        stats = build_index(vault_path=str(self.vault),
                             output_path=str(self.output), rebuild=False)
        self.assertEqual(stats["unchanged"], 4)
        self.assertEqual(stats["new"], 0)
        self.assertEqual(stats["updated"], 0)

    def test_incremental_picks_up_new_file(self):
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        # Add a new file
        new_path = self.vault / "Framework — Topic C.md"
        new_path.write_text(
            "# Topic C\n\n" + ("Topic C content " * 30),
            encoding="utf-8")
        stats = build_index(vault_path=str(self.vault),
                             output_path=str(self.output), rebuild=False)
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["unchanged"], 4)

    def test_incremental_picks_up_modified_file(self):
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        # Touch a file with new content (and new mtime).
        p = self.vault / "Framework — Topic A.md"
        time.sleep(0.01)  # ensure mtime advances
        p.write_text(p.read_text() + "\n\nNew added content paragraph " * 30,
                      encoding="utf-8")
        stats = build_index(vault_path=str(self.vault),
                             output_path=str(self.output), rebuild=False)
        self.assertEqual(stats["updated"], 1)

    def test_rebuild_flag_recreates_full_index(self):
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        stats = build_index(vault_path=str(self.vault),
                             output_path=str(self.output), rebuild=True)
        self.assertEqual(stats["new"], 4)
        self.assertEqual(stats["unchanged"], 0)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


class TestLookups(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = _make_vault(self.tmp, {
            "Topic A.md": "# Topic A\n\n" + (
                "Quantum entanglement creates non-local correlations between particles "
                "that have interacted in the past, regardless of distance. "
            ) * 5,
            "Topic B.md": "# Topic B\n\n" + (
                "Markov chain Monte Carlo (MCMC) sampling is widely used in Bayesian "
                "statistics for posterior inference when the distribution is intractable. "
            ) * 5,
        })
        self.output = Path(self.tmp) / "vault-index.json"
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        self.index = load_index(str(self.output))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_paragraph_hash_match(self):
        candidate = (
            "Quantum entanglement creates non-local correlations between particles "
            "that have interacted in the past, regardless of distance."
        ) * 5
        matches = find_matches_by_paragraph_hash(candidate, self.index,
                                                   min_overlap=0.5)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["entry"]["vault_path"], "Topic A.md")
        self.assertGreaterEqual(matches[0]["overlap_ratio"], 0.5)

    def test_no_match_for_unrelated_content(self):
        candidate = (
            "The mitochondrion is the powerhouse of the cell and contains its "
            "own DNA inherited maternally in most species. " * 10
        )
        matches = find_matches_by_paragraph_hash(candidate, self.index,
                                                   min_overlap=0.5)
        self.assertEqual(matches, [])

    def test_topic_fingerprint_match(self):
        # Use the actual fingerprint of one of the entries.
        first = self.index["entries"][0]
        fp = first["topic_fingerprint"]
        if not fp:
            self.skipTest("entry has empty fingerprint; skip")
        out = find_matches_by_topic_fingerprint(fp, self.index)
        self.assertGreaterEqual(len(out), 1)
        ids = {e["id"] for e in out}
        self.assertIn(first["id"], ids)


# ---------------------------------------------------------------------------
# iter_vault_files
# ---------------------------------------------------------------------------


class TestIterVaultFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = _make_vault(self.tmp, {
            "A.md": "x",
            "Engrams/B.md": "x",
            "Sessions/C.md": "x",
            "D.md.bak": "x",
            "2026-04-30_12-00_x.md": "x",
            "Workshop/E.md": "x",
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_only_kept_files(self):
        files = list(iter_vault_files(self.vault))
        rels = sorted(str(f.relative_to(self.vault)) for f in files)
        self.assertEqual(rels, ["A.md", "Engrams/B.md", "Workshop/E.md"])


if __name__ == "__main__":
    unittest.main()
