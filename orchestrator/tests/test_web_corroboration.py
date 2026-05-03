"""Tests for orchestrator/tools/web_corroboration.py — Phase 5.5.

Per Reference — Ora YAML Schema §15 (rev 3) the external-tier
classifier runs a four-stage cascade:

    1. Whitelist match (high-provenance)  → "whitelisted" (0.7)
    2. Page-specific override            → override's tier
    3. Corroboration count (≥2 unaffiliated domains in result set)
                                          → "corroborated" (0.3)
    4. Single source                     → "single" (0.15)
    Excluded patterns (any time)         → "excluded" (0.0)

Reference — Trusted Web Sources is loaded at engine startup; reload
triggers on file modification time.

The Trusted Web Sources file also lists "Medium Provenance" patterns
described in the file as "(web-corroborated tier, weight 0.3)".
Phase 5.5 treats Medium Provenance whitelist hits as pre-classified
"corroborated" without requiring corroboration count from a search
result set.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from tools import web_corroboration  # noqa: E402


# Sample trusted-sources content used by most tests below.
SAMPLE_TRUSTED_SOURCES = """---
nexus:
  - ora
type: supervision
---

# Trusted Web Sources

## High Provenance (resource-tier, weight 0.7)

```
pubmed.ncbi.nlm.nih.gov/*
arxiv.org/abs/*
plato.stanford.edu/*
en.wikipedia.org/wiki/Mathematics_*
```

## Medium Provenance (web-corroborated tier, weight 0.3)

```
bbc.com/news/*
reuters.com/*
```

## Page-Specific Overrides

```
en.wikipedia.org/wiki/Some_Specific_Article  → resource
bbc.com/news/world-some-op-ed                → web
```

## Excluded

```
*.medium.com/*
*.substack.com/*
contentfarm.tld/*
```
"""


def _write_registry(path, content=None):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or SAMPLE_TRUSTED_SOURCES)


# ---------------------------------------------------------------------------
# Registry parsing
# ---------------------------------------------------------------------------


class TestRegistryParsing(unittest.TestCase):
    """Loading the markdown file into pattern lists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "trusted.md")
        _write_registry(self.path)

    def test_high_provenance_loaded(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertIn("pubmed.ncbi.nlm.nih.gov/*", reg.high_patterns)
        self.assertIn("arxiv.org/abs/*", reg.high_patterns)
        self.assertEqual(len(reg.high_patterns), 4)

    def test_medium_provenance_loaded(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertIn("bbc.com/news/*", reg.medium_patterns)
        self.assertIn("reuters.com/*", reg.medium_patterns)
        self.assertEqual(len(reg.medium_patterns), 2)

    def test_excluded_loaded(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertIn("*.medium.com/*", reg.excluded_patterns)
        self.assertEqual(len(reg.excluded_patterns), 3)

    def test_overrides_loaded(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertEqual(len(reg.overrides), 2)
        self.assertEqual(
            reg.overrides["en.wikipedia.org/wiki/Some_Specific_Article"],
            "resource",
        )
        self.assertEqual(
            reg.overrides["bbc.com/news/world-some-op-ed"],
            "web",
        )

    def test_comments_and_blanks_ignored(self):
        content = """## High Provenance

```
# This is a comment
arxiv.org/abs/*

# Another comment
pubmed.ncbi.nlm.nih.gov/*
```
"""
        _write_registry(self.path, content)
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertEqual(len(reg.high_patterns), 2)

    def test_empty_sections(self):
        content = """## High Provenance

```
```

## Excluded

```
```
"""
        _write_registry(self.path, content)
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertEqual(reg.high_patterns, [])
        self.assertEqual(reg.excluded_patterns, [])

    def test_missing_file_returns_empty_registry(self):
        # Defensive: missing file → empty registry, not exception.
        reg = web_corroboration.TrustedSourcesRegistry("/tmp/nonexistent_xyz.md")
        self.assertEqual(reg.high_patterns, [])
        self.assertEqual(reg.medium_patterns, [])
        self.assertEqual(reg.excluded_patterns, [])


# ---------------------------------------------------------------------------
# URL pattern matching
# ---------------------------------------------------------------------------


class TestURLMatching(unittest.TestCase):
    """Glob-style URL pattern matching, protocol-tolerant."""

    def test_strip_https_prefix(self):
        # Patterns don't include the protocol; the matcher must strip it.
        self.assertTrue(web_corroboration._matches_pattern(
            "https://pubmed.ncbi.nlm.nih.gov/12345",
            "pubmed.ncbi.nlm.nih.gov/*",
        ))

    def test_strip_http_prefix(self):
        self.assertTrue(web_corroboration._matches_pattern(
            "http://arxiv.org/abs/2401.00001",
            "arxiv.org/abs/*",
        ))

    def test_no_protocol(self):
        self.assertTrue(web_corroboration._matches_pattern(
            "arxiv.org/abs/2401.00001",
            "arxiv.org/abs/*",
        ))

    def test_glob_wildcard(self):
        self.assertTrue(web_corroboration._matches_pattern(
            "https://en.wikipedia.org/wiki/Mathematics_in_ancient_Egypt",
            "en.wikipedia.org/wiki/Mathematics_*",
        ))
        self.assertFalse(web_corroboration._matches_pattern(
            "https://en.wikipedia.org/wiki/Biology_of_cells",
            "en.wikipedia.org/wiki/Mathematics_*",
        ))

    def test_subdomain_wildcard(self):
        self.assertTrue(web_corroboration._matches_pattern(
            "https://user.medium.com/article",
            "*.medium.com/*",
        ))
        self.assertFalse(web_corroboration._matches_pattern(
            "https://medium.com/article",
            "*.medium.com/*",
        ))

    def test_query_string_ignored_by_path_match(self):
        # A pattern matching a URL prefix should still match when the
        # URL carries a query string.
        self.assertTrue(web_corroboration._matches_pattern(
            "https://arxiv.org/abs/2401.00001?utm_source=foo",
            "arxiv.org/abs/*",
        ))


# ---------------------------------------------------------------------------
# Classification cascade
# ---------------------------------------------------------------------------


class TestClassifyWebSource(unittest.TestCase):
    """The four-stage cascade from Schema §15, with Medium Provenance
    pre-classification per the trusted-sources file's tier note."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "trusted.md")
        _write_registry(self.path)
        self.reg = web_corroboration.TrustedSourcesRegistry(self.path)

    def _classify(self, url, all_urls=None):
        return web_corroboration.classify_web_source(
            url, all_urls=all_urls or [url], registry=self.reg,
        )

    def test_high_provenance_match(self):
        self.assertEqual(
            self._classify("https://pubmed.ncbi.nlm.nih.gov/12345"),
            "whitelisted",
        )

    def test_medium_provenance_match(self):
        self.assertEqual(
            self._classify("https://bbc.com/news/world-something"),
            "corroborated",
        )

    def test_excluded_match(self):
        self.assertEqual(
            self._classify("https://user.medium.com/article"),
            "excluded",
        )

    def test_excluded_overrides_corroboration(self):
        # Even with multiple unaffiliated sources, excluded patterns
        # are filtered before any other classification.
        result = self._classify(
            "https://user.medium.com/article",
            all_urls=[
                "https://user.medium.com/article",
                "https://example.com/article",
                "https://other.org/article",
            ],
        )
        self.assertEqual(result, "excluded")

    def test_page_override_to_resource(self):
        # Page-specific override: this Wikipedia article is upgraded
        # to "resource" tier even though its parent path is not
        # whitelisted.
        self.assertEqual(
            self._classify("https://en.wikipedia.org/wiki/Some_Specific_Article"),
            "resource",
        )

    def test_page_override_to_web(self):
        # Override downgrade: this BBC op-ed gets routed to "web" tier
        # even though bbc.com/news/* is medium-provenance.
        self.assertEqual(
            self._classify("https://bbc.com/news/world-some-op-ed"),
            "web",
        )

    def test_corroboration_count_two_unaffiliated(self):
        # Unknown URL, but ≥2 unaffiliated domains in the result set.
        result = self._classify(
            "https://example.com/article",
            all_urls=[
                "https://example.com/article",
                "https://other.org/article",
                "https://third.io/something",
            ],
        )
        self.assertEqual(result, "corroborated")

    def test_corroboration_count_two_affiliated_does_not_corroborate(self):
        # Same parent domain → affiliated → doesn't corroborate.
        result = self._classify(
            "https://example.com/article",
            all_urls=[
                "https://example.com/article",
                "https://news.example.com/another",
            ],
        )
        # No unaffiliated corroborators → single source.
        self.assertEqual(result, "single")

    def test_single_source(self):
        result = self._classify(
            "https://example.com/article",
            all_urls=["https://example.com/article"],
        )
        self.assertEqual(result, "single")

    def test_high_provenance_takes_priority(self):
        # Whitelist beats corroboration count.
        result = self._classify(
            "https://arxiv.org/abs/2401.00001",
            all_urls=[
                "https://arxiv.org/abs/2401.00001",
                "https://other.com/citation",
                "https://third.org/citation",
            ],
        )
        self.assertEqual(result, "whitelisted")


# ---------------------------------------------------------------------------
# Reload on mtime change
# ---------------------------------------------------------------------------


class TestReloadOnMtime(unittest.TestCase):
    """Engine startup loads; mtime change triggers reload (Schema §15)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "trusted.md")
        _write_registry(self.path)

    def test_initial_load(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        self.assertIn("arxiv.org/abs/*", reg.high_patterns)

    def test_reload_picks_up_changes(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        original_count = len(reg.high_patterns)

        # Wait long enough for mtime resolution + bump it.
        time.sleep(0.05)
        new_content = SAMPLE_TRUSTED_SOURCES.replace(
            "arxiv.org/abs/*",
            "arxiv.org/abs/*\nnewdomain.org/*",
        )
        _write_registry(self.path, new_content)
        os.utime(self.path, (time.time() + 1, time.time() + 1))

        reg.reload_if_changed()
        self.assertGreater(len(reg.high_patterns), original_count)
        self.assertIn("newdomain.org/*", reg.high_patterns)

    def test_no_reload_when_unchanged(self):
        reg = web_corroboration.TrustedSourcesRegistry(self.path)
        before = list(reg.high_patterns)
        reg.reload_if_changed()
        self.assertEqual(reg.high_patterns, before)


if __name__ == "__main__":
    unittest.main()
