"""External-tier classifier — Phase 5.5.

Implements the four-stage cascade from Reference — Ora YAML Schema §15
(rev 3, 2026-04-30) for live web fetches:

    1. Whitelist match (high-provenance) → "whitelisted" (0.7)
    2. Page-specific override            → override's declared tier
    3. Corroboration count (≥2 unaffiliated domains in result set)
                                          → "corroborated" (0.3)
    4. Single source                     → "single" (0.15)
    Excluded patterns (any time)         → "excluded" (0.0)

Trusted-sources patterns load from Reference — Trusted Web Sources at
engine startup; reload triggers on file modification time. Patterns
are glob-style (fnmatch syntax). Page-specific overrides take
precedence over domain-level rules.

The trusted-sources file's "Medium Provenance" section maps to the
"corroborated" classification — the file's parenthetical describes it
as "(web-corroborated tier, weight 0.3)". Phase 5.5 treats Medium
Provenance whitelist hits as pre-classified corroborated without
requiring an actual corroboration count.
"""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Optional


_DEFAULT_TRUSTED_SOURCES_PATH = os.path.expanduser(
    "~/Documents/vault/Reference — Trusted Web Sources.md"
)


# ---------------------------------------------------------------------------
# URL normalization and matching
# ---------------------------------------------------------------------------


_PROTOCOL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _strip_protocol(url: str) -> str:
    """Remove the http:// or https:// prefix from a URL."""
    return _PROTOCOL_RE.sub("", url)


def _matches_pattern(url: str, pattern: str) -> bool:
    """Glob-style URL match. Strips protocol from URL before matching."""
    normalized = _strip_protocol(url)
    return fnmatch.fnmatchcase(normalized, pattern)


def _extract_root_domain(url: str) -> str:
    """Extract a root-domain proxy for affiliation checking.

    Uses the last two dot-separated components (e.g.,
    `news.example.com` → `example.com`). This is a heuristic — fully
    correct extraction would need the public-suffix list, which Phase
    5.5 doesn't depend on. False-positive affiliation (treating sibling
    domains under the same TLD-class as affiliated) is the conservative
    direction here.
    """
    host = _strip_protocol(url).split("/", 1)[0].lower()
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


# ---------------------------------------------------------------------------
# Trusted Sources Registry
# ---------------------------------------------------------------------------


_SECTION_HEADERS = {
    "high":     re.compile(r"^##\s+High Provenance",    re.MULTILINE | re.IGNORECASE),
    "medium":   re.compile(r"^##\s+Medium Provenance",  re.MULTILINE | re.IGNORECASE),
    "override": re.compile(r"^##\s+Page-Specific Overrides", re.MULTILINE | re.IGNORECASE),
    "excluded": re.compile(r"^##\s+Excluded",           re.MULTILINE | re.IGNORECASE),
}

_NEXT_SECTION_RE = re.compile(r"^##\s", re.MULTILINE)
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_OVERRIDE_LINE_RE = re.compile(r"^\s*(\S.*?\S)\s+→\s+(\S+)\s*$")


class TrustedSourcesRegistry:
    """Loads and caches the trusted-sources whitelist.

    Reload triggers on file mtime change (Schema §15). Missing file
    yields an empty registry rather than raising — a defensively-empty
    registry just causes everything to fall through to the
    corroboration-count / single-source path.
    """

    def __init__(self, path: str = _DEFAULT_TRUSTED_SOURCES_PATH):
        self.path = path
        self.high_patterns:    list[str] = []
        self.medium_patterns:  list[str] = []
        self.excluded_patterns: list[str] = []
        self.overrides:        dict[str, str] = {}
        self._mtime: float = 0.0
        self.reload()

    def reload(self) -> None:
        """(Re)parse the trusted-sources file from disk."""
        self.high_patterns = []
        self.medium_patterns = []
        self.excluded_patterns = []
        self.overrides = {}

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read()
            self._mtime = os.path.getmtime(self.path)
        except (OSError, FileNotFoundError):
            self._mtime = 0.0
            return

        sections = self._slice_sections(content)
        self.high_patterns     = self._extract_patterns(sections.get("high", ""))
        self.medium_patterns   = self._extract_patterns(sections.get("medium", ""))
        self.excluded_patterns = self._extract_patterns(sections.get("excluded", ""))
        self.overrides         = self._extract_overrides(sections.get("override", ""))

    def reload_if_changed(self) -> bool:
        """Reload if the file's mtime is newer than last load. Returns
        True when a reload happened."""
        try:
            mtime = os.path.getmtime(self.path)
        except (OSError, FileNotFoundError):
            return False
        if mtime > self._mtime:
            self.reload()
            return True
        return False

    @staticmethod
    def _slice_sections(content: str) -> dict[str, str]:
        """Split the file into its named sections."""
        out: dict[str, str] = {}
        for name, header_re in _SECTION_HEADERS.items():
            m = header_re.search(content)
            if not m:
                continue
            start = m.end()
            # Find the next ## heading after this one.
            next_match = _NEXT_SECTION_RE.search(content, start)
            end = next_match.start() if next_match else len(content)
            out[name] = content[start:end]
        return out

    @staticmethod
    def _extract_patterns(section: str) -> list[str]:
        """Extract pattern lines from the first code-fence in a section."""
        if not section:
            return []
        fence_match = _FENCE_RE.search(section)
        if not fence_match:
            return []
        body = fence_match.group(1)
        patterns: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            # Skip override-shaped lines (those have an arrow).
            if "→" in stripped:
                continue
            patterns.append(stripped)
        return patterns

    @staticmethod
    def _extract_overrides(section: str) -> dict[str, str]:
        """Extract `pattern → tier` overrides from the section's code fence."""
        if not section:
            return {}
        fence_match = _FENCE_RE.search(section)
        if not fence_match:
            return {}
        body = fence_match.group(1)
        overrides: dict[str, str] = {}
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = _OVERRIDE_LINE_RE.match(stripped)
            if not m:
                continue
            pattern, tier = m.group(1).strip(), m.group(2).strip()
            # Strip any trailing parens (e.g., "resource (0.7)" → "resource")
            tier = tier.split("(")[0].strip()
            overrides[pattern] = tier
        return overrides

    def matches_high(self, url: str) -> bool:
        return any(_matches_pattern(url, p) for p in self.high_patterns)

    def matches_medium(self, url: str) -> bool:
        return any(_matches_pattern(url, p) for p in self.medium_patterns)

    def matches_excluded(self, url: str) -> bool:
        return any(_matches_pattern(url, p) for p in self.excluded_patterns)

    def get_override(self, url: str) -> Optional[str]:
        """Return the override tier for `url`, or None if no override
        applies. Override pattern matching uses the same glob rules as
        whitelist matching."""
        for pattern, tier in self.overrides.items():
            if _matches_pattern(url, pattern):
                return tier
        return None


# ---------------------------------------------------------------------------
# Module-level cached registry (for the production engine startup path)
# ---------------------------------------------------------------------------


_module_registry: Optional[TrustedSourcesRegistry] = None


def get_default_registry() -> TrustedSourcesRegistry:
    """Lazy-load the production trusted-sources registry.

    Phase 5.6 callers will use this; tests pass their own registry via
    `classify_web_source(..., registry=stub)`.
    """
    global _module_registry
    if _module_registry is None:
        _module_registry = TrustedSourcesRegistry(_DEFAULT_TRUSTED_SOURCES_PATH)
    else:
        _module_registry.reload_if_changed()
    return _module_registry


# ---------------------------------------------------------------------------
# Classification cascade
# ---------------------------------------------------------------------------


def classify_web_source(
    url: str,
    all_urls: Optional[list[str]] = None,
    *,
    registry: Optional[TrustedSourcesRegistry] = None,
) -> str:
    """Classify a web URL per the Schema §15 cascade.

    Args:
        url: the URL being scored.
        all_urls: the full set of result URLs (used for corroboration
            count). Defaults to [url] (single-source).
        registry: trusted-sources registry. Defaults to the
            production lazy-loaded registry.

    Returns one of: "whitelisted", "corroborated", "single",
    "excluded", or an override-declared tier name (e.g., "resource",
    "web") when a page-specific override applies.
    """
    if registry is None:
        registry = get_default_registry()

    # Stage 0: excluded patterns filter before anything else.
    if registry.matches_excluded(url):
        return "excluded"

    # Stage 2 (per §15): page-specific override beats domain-level rules.
    override = registry.get_override(url)
    if override:
        return override

    # Stage 1: high-provenance whitelist.
    if registry.matches_high(url):
        return "whitelisted"

    # Medium-provenance whitelist → pre-classified "corroborated".
    if registry.matches_medium(url):
        return "corroborated"

    # Stage 3: corroboration count from the result set. Excluded URLs
    # in the candidate set don't contribute to the count (they'd be
    # filtered out themselves before ranking).
    candidates = all_urls or [url]
    own_root = _extract_root_domain(url)
    unaffiliated_roots = {
        _extract_root_domain(u)
        for u in candidates
        if _extract_root_domain(u) != own_root
        and not registry.matches_excluded(u)
    }
    if len(unaffiliated_roots) >= 2:
        return "corroborated"

    # Stage 4: single non-farm source.
    return "single"


__all__ = [
    "TrustedSourcesRegistry",
    "classify_web_source",
    "get_default_registry",
    "_matches_pattern",
    "_strip_protocol",
    "_extract_root_domain",
]
