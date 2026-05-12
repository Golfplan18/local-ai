"""Article image sweeper — find news articles in the MSI Astro repo that
are missing an ``image:`` frontmatter field, build an image-generation
request from each article's existing frontmatter, and run them through
``render_news_image``.

This is the auto-trigger piece that closes the gap between "publisher
generates an article via the AI framework" and "the article ships with
an image attached." Two entry points:

  1. :func:`sweep_once` — single-pass scan + render of any articles
     missing images. Returns a structured summary. Suitable for the
     ``/render-missing-article-images`` slash command and for periodic
     invocation by the oversight daemon (Ora's polling sweeper pattern).

  2. :func:`build_request_from_article` — pure function that turns an
     article's parsed frontmatter into the NewsImageRequest dict that
     ``render_news_image`` expects. Exposed for testing and for callers
     that want to build a request without invoking the renderer.

The sweeper is intentionally conservative: it skips articles where the
``image:`` field is already present (even if it's a placeholder), and
it skips articles marked ``draft: true`` so unfinished work doesn't
burn Buzz on placeholder renders. The publisher can force a re-render
by deleting the ``image:`` field from a specific article and re-running.

Per ``Framework — News Image Generator.md`` Layer 1 (Request Validation
and Style Routing) — the sweeper materializes the request object that
the framework's architectural note describes as "emitted by the article
generator alongside the article." Until the article generator is wired
to emit this object directly, the sweeper derives it from the article's
own frontmatter.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

# Same path setup as the other orchestrator modules.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from msi_image_render import (  # noqa: E402
    ASTRO_ARTICLES_DIR,
    render_news_image,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_REGISTER = "illustrated"
# Articles with explicit register hints in their primary_themes or
# section frontmatter could be classified differently; the v1 sweeper
# uses "illustrated" as the safe default because the LoRA refuses
# non-Hector prompts and gpt-image-1's illustrated register lands well
# on the canonical sample articles.


@dataclass
class SweepResult:
    """Structured summary of a sweep_once() pass."""
    scanned: int = 0
    skipped_has_image: int = 0
    skipped_draft: int = 0
    skipped_parse_error: int = 0
    rendered: list[dict] = field(default_factory=list)  # list of per-article render results
    failed: list[dict] = field(default_factory=list)    # list of {slug, error}


# ---------------------------------------------------------------------------
# Frontmatter parser (minimal — handles the shape Astro requires)
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Returns ({}, text) when no
    frontmatter is present. Uses a deliberately minimal YAML parser
    that handles only the field shapes the Astro article schema uses
    (string scalars, multiline ``|`` blocks, simple lists). Good enough
    for "does this article have an image: field" + "what's the
    headline/lede" — full YAML round-trip lives in the renderer.
    """
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.DOTALL)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = m.group(2)

    fm: dict = {}
    current_key: Optional[str] = None
    multiline_lines: list[str] = []
    multiline_mode: Optional[str] = None  # "|" or ">"

    for line in fm_text.split("\n"):
        if multiline_mode is not None:
            # Continue collecting multiline content until we hit a
            # non-indented line (next key) or EOF.
            if line.startswith(" ") or line == "":
                multiline_lines.append(line.lstrip())
                continue
            # End of multiline — flush.
            fm[current_key] = "\n".join(multiline_lines).rstrip()
            multiline_mode = None
            multiline_lines = []
            # Fall through to process this line as a fresh key.

        # Top-level "key:" or "key: value"
        m2 = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$', line)
        if not m2:
            continue
        key = m2.group(1)
        value = m2.group(2).strip()
        if value == "|" or value == ">":
            current_key = key
            multiline_mode = value
            multiline_lines = []
        elif value == "":
            # Nested block (dict or list) — record presence but don't
            # parse contents. "image: \n  url: ..." sets fm["image"] to
            # an empty string sentinel that callers treat as present.
            fm[key] = "<<NESTED>>"
            current_key = key
        else:
            fm[key] = _strip_yaml_quotes(value)
            current_key = key
    # Flush any trailing multiline
    if multiline_mode is not None and current_key is not None:
        fm[current_key] = "\n".join(multiline_lines).rstrip()
    return fm, body


def _strip_yaml_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------

def build_request_from_article(slug: str, frontmatter: dict,
                               *, register: str = DEFAULT_REGISTER) -> dict:
    """Build a NewsImageRequest dict from an article's parsed frontmatter.

    The article's ``headline`` and ``lede`` become the prompt-construction
    seeds. The visual_register defaults to ``illustrated`` since:
      - The LoRA dispatcher refuses non-Hector prompts (so a misclassified
        photographic register won't accidentally activate Hector style).
      - gpt-image-1 + Gemini handle the ``illustrated`` register cleanly.
      - The publisher can override per-article by writing a request JSON
        directly and calling ``/news-image-render <request.json>``.

    No real-individual entities are auto-populated; the v1 sweeper
    treats articles as not naming public figures (the likeness gate is
    a defensive default — entities can only be added by the article
    generator emitting them, which it doesn't yet).
    """
    headline = frontmatter.get("headline", "").strip()
    lede = frontmatter.get("lede", "").strip()
    # Build prompt seeds from headline + a compact lede summary
    seeds = [headline] if headline else []
    if lede:
        # Trim the lede to the first sentence or so to avoid overlong
        # prompts. gpt-image-1 handles long prompts but illustrated
        # outputs are cleaner with a focused subject.
        first_sentence = re.split(r'(?<=[.!?])\s+', lede.replace("\n", " "), maxsplit=1)[0]
        if first_sentence and first_sentence != headline:
            seeds.append(first_sentence)
    seeds.append("editorial illustration palette, documentary illustration style")

    return {
        "article_slug": slug,
        "article_headline": headline or slug,
        "article_lede": lede,
        "visual_register": register,
        "prompt_seeds": seeds,
        "primary_entities": [],
        "style_spec_version": "current",
        "source_path_strategy": "ai_only",
    }


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def sweep_once(articles_dir: str = ASTRO_ARTICLES_DIR,
               *, dry_run: bool = False,
               include_drafts: bool = False) -> SweepResult:
    """Scan ``articles_dir`` for .md articles missing an ``image:`` field
    and render each via ``render_news_image``.

    Skips:
      - Files where ``image:`` is already in the frontmatter (any
        existing value counts as "has image"; the publisher must
        delete the field to force a re-render).
      - Drafts (``draft: true``) unless ``include_drafts=True``.
      - Files that can't be parsed as frontmatter.

    Returns a :class:`SweepResult` with per-article outcomes. When
    ``dry_run=True``, the function reports what would be rendered
    without actually invoking the renderer (useful for verifying which
    articles would be processed before spending Buzz).
    """
    result = SweepResult()
    if not os.path.isdir(articles_dir):
        return result

    for filename in sorted(os.listdir(articles_dir)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(articles_dir, filename)
        if not os.path.isfile(path):
            continue

        result.scanned += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            result.skipped_parse_error += 1
            continue

        frontmatter, _body = _split_frontmatter(text)
        if not frontmatter:
            result.skipped_parse_error += 1
            continue

        # Skip articles already carrying an image: field (top-level
        # nested block or single-line value).
        if "image" in frontmatter:
            result.skipped_has_image += 1
            continue

        if not include_drafts:
            draft_value = frontmatter.get("draft", "").lower()
            if draft_value == "true":
                result.skipped_draft += 1
                continue

        slug = filename[:-3]  # strip .md
        request = build_request_from_article(slug, frontmatter)

        if dry_run:
            result.rendered.append({
                "slug": slug,
                "dry_run": True,
                "request": request,
            })
            continue

        try:
            render_result = render_news_image(request)
            if render_result.get("success"):
                result.rendered.append({
                    "slug": slug,
                    "image_path": render_result.get("image_path"),
                    "provider": render_result.get(
                        "image_schema", {}).get("ai_model"),
                    "article_md_updated": render_result.get(
                        "article_md_updated", False),
                    "attempts": render_result.get("attempts") or [],
                })
            else:
                result.failed.append({
                    "slug": slug,
                    "error": render_result.get("error", "<unknown>"),
                })
        except Exception as exc:
            result.failed.append({
                "slug": slug,
                "error": f"{type(exc).__name__}: {exc}",
            })

    return result


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    res = sweep_once(dry_run=dry)
    print(f"scanned={res.scanned} "
          f"has_image={res.skipped_has_image} "
          f"drafts={res.skipped_draft} "
          f"parse_errors={res.skipped_parse_error} "
          f"rendered={len(res.rendered)} "
          f"failed={len(res.failed)}")
    for r in res.rendered:
        print(f"  ✓ {r['slug']}"
              + (f" → {r.get('provider', '?')}"
                 if not r.get("dry_run") else " (DRY RUN)"))
    for f_ in res.failed:
        print(f"  ✗ {f_['slug']}: {f_['error']}")
