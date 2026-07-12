"""Phase 3 — extract news, opinion, and resource pasted segments
from the cleaned-pair archive into structured vault notes.

For each pasted segment in `~/Documents/Commercial AI archives/`
classified as `news`, `opinion`, or `resource`:

  - Send the segment content to Sonnet with a type-specific extraction
    prompt that returns JSON (headline, lede, key facts, quotes, etc.)
  - Template the JSON into a Schema §12-compatible vault note
  - For opinion: also capture the user's reaction (the personal-voice
    portions of the same pair's `cleaned_user_input`)
  - Write to the FLAT `~/Documents/vault/Resources/` folder (vault
    convention since Schema rev 5, 2026-05-09: kind lives in YAML
    `tags`, not in folder structure — no News/Opinion/Resources or
    year subfolders)
  - Index each written note into ChromaDB's `knowledge` collection so
    it is immediately retrievable (type: resource → provenance weight
    0.8 at query time)

A manifest at `~/ora/data/phase3-manifest.json` tracks per-segment
completion so re-runs skip already-extracted segments. Segment id is
`<file_basename>_seg<N>` where N is the segment's index within the
pair.

Output filename: `YYYY-MM-DD_<slug>.md` (slug derived from headline /
title, sanitized to lowercase ASCII + hyphens). Collisions append
`-seg<N>` to disambiguate.

Own-fiction guard: phase 3 once swept the user's own fiction drafts
(pasted manuscript chunks misclassified as opinion/news) into 97 junk
source notes — see vault `Archive/Misfiled Fiction Extractions/`. Two
cheap heuristics now skip the obvious cases (very large dialogue-heavy
pastes pre-call; "unable to determine"-titled extractions post-call).
Both fail OPEN with loud logging: a guard error never blocks
extraction, and an uncertain segment is extracted rather than dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)
from orchestrator.historical.paste_detection import (
    Segment,
    process_user_input,
)
from orchestrator.historical.chain_detector import (
    derive_session_id,
    load_chain_index,
    CHAIN_INDEX_DEFAULT,
)


# ---------------------------------------------------------------------------
# Annotation block parsing (read LLM-set classifications, not heuristic)
# ---------------------------------------------------------------------------

_ANNOTATION_BLOCK_RE = re.compile(
    r"#### Pasted segments\b.*?(?=\n### |\Z)",
    re.DOTALL,
)
_SEGMENT_ENTRY_RE = re.compile(
    r"\*\*Segment (\d+)\*\* — type=`([^`]+)`",
)


def _read_classifications_from_annotation(file_text: str) -> dict[int, str]:
    """Parse the `#### Pasted segments` annotation block and return
    {segment_index_1based: classification}. Empty dict if no annotation
    block. Authoritative source for classifications because the LLM
    reclassifier writes here; re-running heuristic classification would
    lose those updates."""
    block_m = _ANNOTATION_BLOCK_RE.search(file_text)
    if not block_m:
        return {}
    out: dict[int, str] = {}
    for m in _SEGMENT_ENTRY_RE.finditer(block_m.group(0)):
        out[int(m.group(1))] = m.group(2)
    return out


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ARCHIVE_DIR    = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_RESOURCES_ROOT = "/Users/oracle/Documents/vault/Resources"
DEFAULT_MANIFEST_PATH  = "/Users/oracle/ora/data/phase3-manifest.json"
DEFAULT_REPORT_PATH    = "/Users/oracle/ora/data/phase3-report.json"

# Sonnet 4.5 — chosen for extraction quality per user direction.
EXTRACTION_MODEL = "claude-sonnet-4-5"

# Don't bother extracting tiny segments — the heuristic + LLM classifier
# can mis-tag dialogue snippets; a sub-300-char segment isn't worth a
# Sonnet call and rarely yields a usable extraction.
MIN_SEGMENT_CHARS = 300

# Cap input sent to Sonnet — long articles still extract well from
# the first ~6K chars.
MAX_INPUT_CHARS_PER_SEGMENT = 6_000

# --- Own-fiction guard thresholds (PROVISIONAL — uncalibrated) -------------
# Set from inspection of the 97 misfiled fiction extractions (vault
# Archive/Misfiled Fiction Extractions/, cleaned up 2026-07-12): those
# pastes were manuscript-sized (up to ~750K chars) and dialogue-heavy,
# while genuinely pasted articles run ~3-10K chars. Retune against real
# skip logs if the guard proves too eager or too lax.
FICTION_GUARD_MIN_CHARS = 20_000     # guard only engages above this size
FICTION_DIALOGUE_LINE_FRACTION = 0.15  # fraction of lines carrying dialogue quotes

_CHAPTER_HEADING_RE = re.compile(r"^\s*(?:#+\s*)?chapter\s+\d+", re.IGNORECASE | re.MULTILINE)
_DIALOGUE_QUOTE_CHARS = ('"', '“', '”')


# ---------------------------------------------------------------------------
# Extraction prompts (one per type)
# ---------------------------------------------------------------------------


_NEWS_PROMPT = """\
You are extracting structured information from a pasted news article. The \
article was pasted into a chat conversation by the user; extract its key \
content into JSON. Be faithful to what's written — do not embellish, \
summarize past what's stated, or invent details.

Required JSON shape:

{
  "headline":   "string (the article's headline; if no clear headline, infer one from the lede)",
  "source":     "string or null (publication name if identifiable from the text)",
  "date":       "string or null (article date in YYYY-MM-DD if mentioned)",
  "lede":       "string (the article's opening 1-3 sentences — the core news summary)",
  "key_facts":  ["string", ...]  (3-7 important factual claims, each one sentence),
  "key_quotes": [{"quote": "...", "speaker": "...", "context": "..."}, ...]  (up to 5),
  "context":    "string (background information mentioned in the article, 1-2 short paragraphs)"
}

Reply with the JSON object ONLY — no preamble, no fences, no commentary."""


_OPINION_PROMPT = """\
You are extracting structured information from a pasted opinion piece \
(op-ed, columnist, blog post, substack-style essay). Extract its argument \
into JSON. Stay faithful to the author's stated position.

Required JSON shape:

{
  "headline":         "string (the title of the piece; if missing, infer from the lede)",
  "source":           "string or null (publication / blog name if identifiable)",
  "author":           "string or null (byline if mentioned)",
  "date":             "string or null (date in YYYY-MM-DD if mentioned)",
  "lede":             "string (opening 1-3 sentences)",
  "argument_stance":  "string (one sentence: what is the author's position?)",
  "key_claims":       ["string", ...]  (3-7 supporting claims),
  "key_quotes":       [{"quote": "...", "speaker": "...", "context": "..."}, ...] (notable phrases, up to 5),
  "context":          "string (any background the author cites)"
}

Reply with the JSON object ONLY — no preamble, no fences, no commentary."""


_RESOURCE_PROMPT = """\
You are extracting structured information from a pasted reference \
document — a research paper, technical doc, formal study, or similar \
material. Stay faithful to what's written.

Required JSON shape:

{
  "title":          "string (document title; infer from first heading or first sentence)",
  "source":         "string or null (publication / publisher if identifiable)",
  "date":           "string or null (date in YYYY-MM-DD if mentioned)",
  "topic_summary":  "string (1-2 sentences: what does this document cover?)",
  "key_points":     ["string", ...]  (3-10 takeaways, each one sentence),
  "citations":      ["string", ...]  (any citation strings — DOI, paper refs, etc.)
}

Reply with the JSON object ONLY — no preamble, no fences, no commentary."""


_PROMPT_BY_TYPE = {
    "news":     _NEWS_PROMPT,
    "opinion":  _OPINION_PROMPT,
    "resource": _RESOURCE_PROMPT,
}


# ---------------------------------------------------------------------------
# Segment lookup + iteration
# ---------------------------------------------------------------------------


@dataclass
class ExtractionTarget:
    """One pasted segment that needs Phase 3 extraction."""
    file_path:        str
    pair_num:         int
    when:             Optional[datetime]
    source_chat:      str
    source_platform:  str
    chain_id:         str
    chain_label:      str
    seg_index:        int
    seg_kind:         str        # 'news' | 'opinion' | 'resource'
    content:          str
    user_voice:       str        # personal-voice portions of the same pair


def _user_voice_only(cp: CleanedPairFile) -> str:
    """Return the personal-voice portions of cleaned_user_input, paste-free.
    Mirrors path2_orchestrator._user_voice_only. Used so opinion notes can
    capture the user's reaction context without pasting the same article
    back."""
    if not cp.cleaned_user_input:
        return ""
    segments = process_user_input(
        cp.cleaned_user_input,
        vault_index=None,
        source_platform=cp.source_platform,
    )
    parts = [s.content for s in segments if s.kind == "personal"]
    return "\n\n".join(parts).strip()


def find_extraction_targets(
    file_path: str,
    *,
    chain_lookup: Optional[dict] = None,
) -> list[ExtractionTarget]:
    """Walk one cleaned-pair file and return all news/opinion/resource
    segments above MIN_SEGMENT_CHARS as ExtractionTarget records.

    Classifications come from the file's `#### Pasted segments`
    annotation block (which holds the LLM-set classifications). We
    re-run paste detection only to recover segment CONTENT and BOUNDARIES;
    the heuristic classification it returns is overridden by what the
    annotation block records.
    """
    cp = load_cleaned_pair(file_path)
    file_text = Path(file_path).read_text(encoding="utf-8")
    annotation_classes = _read_classifications_from_annotation(file_text)

    segments = process_user_input(
        cp.cleaned_user_input,
        vault_index=None,
        source_platform=cp.source_platform,
    )
    user_voice = _user_voice_only(cp)
    sid = derive_session_id(cp.source_chat)
    if chain_lookup:
        chain_id = chain_lookup.get("session_to_chain", {}).get(sid, "")
        chain_label = ""
        if chain_id:
            for c in chain_lookup.get("chains", []):
                if c["chain_id"] == chain_id:
                    chain_label = c["chain_label"]
                    break
    else:
        chain_id = ""
        chain_label = ""

    # Track 1-based pasted-segment index so we can match against the
    # annotation block (which numbers segments 1, 2, 3 in pasted order).
    pasted_idx = 0
    out: list[ExtractionTarget] = []
    for i, seg in enumerate(segments):
        if seg.kind != "pasted":
            continue
        pasted_idx += 1
        # Use annotation classification when available; fall back to
        # heuristic if the file lacks an annotation (older pre-reclass
        # file).
        cls = annotation_classes.get(pasted_idx, seg.classification)
        if cls not in ("news", "opinion", "resource"):
            continue
        if len(seg.content) < MIN_SEGMENT_CHARS:
            continue
        out.append(ExtractionTarget(
            file_path=file_path,
            pair_num=cp.source_pair_num,
            when=cp.source_timestamp,
            source_chat=cp.source_chat,
            source_platform=cp.source_platform,
            chain_id=chain_id,
            chain_label=chain_label,
            seg_index=i,
            seg_kind=cls,
            content=seg.content,
            user_voice=user_voice,
        ))
    return out


# ---------------------------------------------------------------------------
# Sonnet call + JSON parsing
# ---------------------------------------------------------------------------


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_json_fences(text: str) -> str:
    """Strip ``` fences if Sonnet wraps its JSON in markdown."""
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1)
    return text.strip()


def extract_segment(
    target: ExtractionTarget,
    *,
    client: AnthropicClient,
) -> tuple[Optional[dict], int, int, float, str]:
    """Run Sonnet extraction. Returns (parsed_json | None, in_tok, out_tok,
    cost_usd, error_msg)."""
    prompt = _PROMPT_BY_TYPE.get(target.seg_kind)
    if prompt is None:
        return None, 0, 0, 0.0, f"unknown seg_kind: {target.seg_kind}"
    truncated = target.content[:MAX_INPUT_CHARS_PER_SEGMENT]
    user_msg = f"<<<TEXT\n{truncated}\nTEXT>>>\n\nExtract:"
    result = client.call(
        system=prompt,
        user=user_msg,
        model=EXTRACTION_MODEL,
        max_tokens=2048,
        temperature=0.0,
    )
    if result.error:
        return None, result.input_tokens, result.output_tokens, result.cost_usd, result.error
    raw = _strip_json_fences(result.text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, result.input_tokens, result.output_tokens, result.cost_usd, f"json parse: {e}: {raw[:200]}"
    return parsed, result.input_tokens, result.output_tokens, result.cost_usd, ""


# ---------------------------------------------------------------------------
# Own-fiction guard (fail-open: an error here never blocks extraction)
# ---------------------------------------------------------------------------


def fiction_guard_reason(content: str) -> str:
    """Pre-call heuristic: return a reason string when a pasted segment
    looks like the user's own fiction manuscript rather than a pasted
    article, or "" to proceed with extraction.

    Only engages on very large pastes (articles are ~3-10K chars;
    manuscript pastes in the misfiled-fiction corpus ran to 750K), and
    then needs a fiction signal on top: dialogue-heavy lines or chapter
    headings. Long research papers pass — low dialogue density, no
    chapter headings.
    """
    try:
        if len(content) < FICTION_GUARD_MIN_CHARS:
            return ""
        lines = [ln for ln in content.split("\n") if ln.strip()]
        if not lines:
            return ""
        dialogue_lines = sum(
            1 for ln in lines
            if any(q in ln for q in _DIALOGUE_QUOTE_CHARS)
        )
        dialogue_fraction = dialogue_lines / len(lines)
        if dialogue_fraction >= FICTION_DIALOGUE_LINE_FRACTION:
            return (f"large paste ({len(content):,} chars) with dialogue-heavy "
                    f"lines ({dialogue_fraction:.0%} ≥ "
                    f"{FICTION_DIALOGUE_LINE_FRACTION:.0%}) — likely own fiction")
        chapter_hits = len(_CHAPTER_HEADING_RE.findall(content))
        if chapter_hits >= 2:
            return (f"large paste ({len(content):,} chars) with {chapter_hits} "
                    f"chapter headings — likely own fiction")
        return ""
    except Exception as e:  # fail OPEN — proceed with extraction
        print(f"[phase3] fiction guard errored ({e}); extracting anyway",
              file=sys.stderr, flush=True)
        return ""


def extraction_self_reports_failure(extracted: dict) -> str:
    """Post-call heuristic: return a reason string when the extraction
    model itself signalled it found no article (the misfiled-fiction
    corpus is full of notes titled \"Unable to determine — …\"), or ""
    to write the note.
    """
    try:
        title = str(extracted.get("headline") or extracted.get("title") or "")
        if title.strip().lower().startswith("unable to determine"):
            return f"extraction self-reported failure: {title[:120]!r}"
        return ""
    except Exception as e:  # fail OPEN — write the note
        print(f"[phase3] self-report guard errored ({e}); writing anyway",
              file=sys.stderr, flush=True)
        return ""


# ---------------------------------------------------------------------------
# Vault note builder + writer
# ---------------------------------------------------------------------------


_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS_RE    = re.compile(r"[\s\-]+")


def _slugify(text: str, max_words: int = 6) -> str:
    """Filename slug: lowercase, alphanumeric + hyphens, capped at N words."""
    if not text:
        return "untitled"
    s = text.lower()
    s = _SLUG_STRIP_RE.sub(" ", s)
    s = _SLUG_WS_RE.sub("-", s).strip("-")
    parts = [p for p in s.split("-") if p]
    if not parts:
        return "untitled"
    return "-".join(parts[:max_words])


def _yaml_escape(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    if any(c in s for c in ":#[]{},&*!|>'\"%@`\n") or s.strip() != s:
        return "'" + s.replace("'", "''") + "'"
    return s


def _list_yaml(values: list[Any], indent: str = "  - ") -> str:
    """Format a list as YAML lines."""
    if not values:
        return ""
    return "\n".join(f"{indent}{_yaml_escape(v)}" for v in values)


def build_vault_note(
    target:    ExtractionTarget,
    extracted: dict,
) -> str:
    """Compose the markdown body for a Phase 3 vault note. Format
    follows the user-confirmed proposal: YAML frontmatter + headline +
    type-specific structured sections + original-excerpt audit block."""
    when = target.when or datetime.now()
    date_str = when.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    rel_source_chat = target.source_chat.replace(
        os.path.expanduser("~/"), "~/",
    )

    yaml_lines = [
        "---",
        "nexus:",
        "type: resource",
        f"tags:",
        f"  - {target.seg_kind}",
        f"date created: {date_str}",
        f"date modified: {today_str}",
        f"source_chat: {_yaml_escape(rel_source_chat)}",
        f"source_pair_num: {target.pair_num}",
        f"source_platform: {target.source_platform}",
        f"source_timestamp: {when.strftime('%Y-%m-%dT%H:%M:%S')}",
    ]
    if target.chain_id:
        yaml_lines.append(f"chain_id: {target.chain_id}")
        yaml_lines.append(f"chain_label: {_yaml_escape(target.chain_label)}")
    yaml_lines.append(f"extracted_from: cleaned-pair")
    yaml_lines.append(f"extraction_model: {EXTRACTION_MODEL}")
    yaml_lines.append(f"processed_at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    yaml_lines.append("---")
    yaml = "\n".join(yaml_lines) + "\n\n"

    if target.seg_kind == "news":
        body = _build_news_body(extracted, target)
    elif target.seg_kind == "opinion":
        body = _build_opinion_body(extracted, target)
    else:  # resource
        body = _build_resource_body(extracted, target)

    excerpt = target.content[:500].rstrip()
    if len(target.content) > 500:
        excerpt += "..."
    audit = (
        "\n\n## Original (excerpt)\n\n"
        "```\n"
        f"{excerpt}\n"
        "```\n"
    )
    return yaml + body + audit


def _build_news_body(extracted: dict, target: ExtractionTarget) -> str:
    headline = extracted.get("headline") or "Untitled news article"
    source   = extracted.get("source") or "unknown"
    date     = extracted.get("date") or "unknown"
    lede     = extracted.get("lede") or ""
    facts    = extracted.get("key_facts") or []
    quotes   = extracted.get("key_quotes") or []
    context  = extracted.get("context") or ""

    parts = [f"# {headline}\n",
              f"**Source:** {source}",
              f"**Date:** {date}",
              f"**Type:** news\n"]
    if lede:
        parts.append("## Lede\n\n" + lede.strip())
    if facts:
        parts.append("## Key Facts\n")
        for f in facts:
            parts.append(f"- {str(f).strip()}")
    if quotes:
        parts.append("\n## Key Quotes\n")
        for q in quotes:
            if not isinstance(q, dict):
                continue
            quote = q.get("quote") or ""
            speaker = q.get("speaker") or ""
            ctx = q.get("context") or ""
            line = f'> "{quote}"'
            attrib_parts = [p for p in [speaker, ctx] if p]
            if attrib_parts:
                line += " — " + ", ".join(attrib_parts)
            parts.append(line)
    if context:
        parts.append("\n## Context\n\n" + context.strip())
    return "\n".join(parts)


def _build_opinion_body(extracted: dict, target: ExtractionTarget) -> str:
    headline = extracted.get("headline") or "Untitled opinion piece"
    source   = extracted.get("source") or "unknown"
    author   = extracted.get("author") or "unknown"
    date     = extracted.get("date") or "unknown"
    lede     = extracted.get("lede") or ""
    stance   = extracted.get("argument_stance") or ""
    claims   = extracted.get("key_claims") or []
    quotes   = extracted.get("key_quotes") or []
    context  = extracted.get("context") or ""

    parts = [f"# {headline}\n",
              f"**Source:** {source}",
              f"**Author:** {author}",
              f"**Date:** {date}",
              f"**Type:** opinion\n"]
    if lede:
        parts.append("## Lede\n\n" + lede.strip())
    if stance:
        parts.append("\n## Argument Stance\n\n" + stance.strip())
    if claims:
        parts.append("\n## Key Claims\n")
        for c in claims:
            parts.append(f"- {str(c).strip()}")
    if quotes:
        parts.append("\n## Key Quotes\n")
        for q in quotes:
            if not isinstance(q, dict):
                continue
            quote = q.get("quote") or ""
            speaker = q.get("speaker") or ""
            ctx = q.get("context") or ""
            line = f'> "{quote}"'
            attrib_parts = [p for p in [speaker, ctx] if p]
            if attrib_parts:
                line += " — " + ", ".join(attrib_parts)
            parts.append(line)
    if context:
        parts.append("\n## Context\n\n" + context.strip())
    if target.user_voice:
        parts.append("\n## User's Reaction\n\n" + target.user_voice)
    return "\n".join(parts)


def _build_resource_body(extracted: dict, target: ExtractionTarget) -> str:
    title    = extracted.get("title") or "Untitled resource"
    source   = extracted.get("source") or "unknown"
    date     = extracted.get("date") or "unknown"
    summary  = extracted.get("topic_summary") or ""
    points   = extracted.get("key_points") or []
    cites    = extracted.get("citations") or []

    parts = [f"# {title}\n",
              f"**Source:** {source}",
              f"**Date:** {date}",
              f"**Type:** resource\n"]
    if summary:
        parts.append("## Topic\n\n" + summary.strip())
    if points:
        parts.append("\n## Key Points\n")
        for p in points:
            parts.append(f"- {str(p).strip()}")
    if cites:
        parts.append("\n## Citations\n")
        for c in cites:
            parts.append(f"- {str(c).strip()}")
    return "\n".join(parts)


def _vault_path_for(target: ExtractionTarget, extracted: dict,
                     resources_root: str) -> Path:
    """Compute the vault output path for an extracted segment.

    FLAT Resources/ layout (Schema rev 5, 2026-05-09): every note lands
    directly in the root — kind is encoded in YAML tags, never in
    folder structure, and there are no year subfolders.
    """
    when = target.when or datetime.now()
    if target.seg_kind in ("news", "opinion"):
        slug_src = extracted.get("headline") or ""
    else:
        slug_src = extracted.get("title") or ""
    slug = _slugify(slug_src) or "untitled"
    base = f"{when.strftime('%Y-%m-%d')}_{slug}.md"
    return Path(resources_root) / base


def write_vault_note(
    target:          ExtractionTarget,
    extracted:       dict,
    resources_root:  str = DEFAULT_RESOURCES_ROOT,
) -> str:
    """Write the vault note. Returns the absolute path written."""
    path = _vault_path_for(target, extracted, resources_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Collision — append seg index to disambiguate.
        path = path.with_name(
            f"{path.stem}-seg{target.seg_index:02d}{path.suffix}"
        )
    content = build_vault_note(target, extracted)
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Knowledge indexing (ChromaDB `knowledge` collection)
# ---------------------------------------------------------------------------


def index_notes_into_knowledge(
    paths: list[str],
    *,
    progress_to_stderr: bool = True,
) -> dict:
    """Index freshly written source notes into ChromaDB's `knowledge`
    collection so they are retrievable immediately (the May 2026 backlog
    needed a manual knowledge_index CLI run — this closes that gap).

    Routes through knowledge_index.get_knowledge_collection(), which
    binds the embedder via orchestrator.embedding's logical→physical
    collection resolution — never a hardcoded physical name. The notes'
    YAML `type: resource` lands in metadata, so the 0.8 provenance
    weight applies at query time automatically.

    Fail OPEN: if ChromaDB/Ollama are unreachable the failure is logged
    loudly and extraction output stands — notes can be indexed later
    with the knowledge_index CLI.
    """
    stats: dict = {"indexed": 0, "skipped": 0, "errors": 0}
    if not paths:
        return stats
    try:
        from orchestrator.tools.knowledge_index import (
            get_knowledge_collection,
            index_file,
        )
        collection = get_knowledge_collection()
        for p in paths:
            try:
                index_file(collection, p, stats, verbose=False)
            except Exception as e:
                stats["errors"] += 1
                print(f"[phase3] KNOWLEDGE-INDEX ERROR (continuing): {p} — {e}",
                      file=sys.stderr, flush=True)
        if progress_to_stderr:
            print(f"[phase3] knowledge index: {stats['indexed']:,} indexed, "
                  f"{stats['skipped']:,} skipped, {stats['errors']:,} errors",
                  file=sys.stderr, flush=True)
    except Exception as e:
        stats["errors"] += 1
        stats["fatal"] = str(e)
        print(f"[phase3] KNOWLEDGE-INDEX UNAVAILABLE (notes written but NOT "
              f"indexed — run knowledge_index.py over vault Resources/ to "
              f"catch up): {e}", file=sys.stderr, flush=True)
    return stats


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _segment_uid(target: ExtractionTarget) -> str:
    """Stable id for a segment — used for resume tracking."""
    return f"{Path(target.file_path).name}#seg{target.seg_index:02d}"


def _load_manifest(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {
            "version":          1,
            "created_at":       datetime.now().isoformat(timespec="seconds"),
            "completed_segments": {},
            "totals": {
                "segments_extracted": 0,
                "segments_written":   0,
                "input_tokens":       0,
                "output_tokens":      0,
                "cost_usd":           0.0,
            },
        }
    return json.loads(p.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict, path: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------


def run_phase3(
    archive_dir:        str = DEFAULT_ARCHIVE_DIR,
    *,
    resources_root:     str = DEFAULT_RESOURCES_ROOT,
    chain_index_path:   str = CHAIN_INDEX_DEFAULT,
    manifest_path:      str = DEFAULT_MANIFEST_PATH,
    max_workers:        int = 6,
    progress_to_stderr: bool = True,
    rebuild_manifest:   bool = False,
    limit:              Optional[int] = None,
    index_to_knowledge: bool = True,
) -> dict:
    """Walk the archive, extract every news/opinion/resource segment,
    write vault notes, and index them into the knowledge collection."""
    start = time.monotonic()

    chain_lookup = load_chain_index(chain_index_path)

    # Step 1: enumerate all extraction targets.
    if progress_to_stderr:
        print("[phase3] enumerating extraction targets…", file=sys.stderr,
              flush=True)
    files = sorted(Path(archive_dir).glob("*.md"))
    targets: list[ExtractionTarget] = []
    for f in files:
        try:
            ts = find_extraction_targets(str(f), chain_lookup=chain_lookup)
            targets.extend(ts)
        except Exception:
            continue
    if limit:
        targets = targets[:limit]
    if progress_to_stderr:
        from collections import Counter as _C
        kinds = _C(t.seg_kind for t in targets)
        kind_str = ", ".join(f"{k}={v}" for k, v in kinds.most_common())
        print(f"[phase3] {len(targets):,} targets across {len(files):,} files "
              f"({kind_str})", file=sys.stderr, flush=True)

    # Step 2: filter against manifest (resume).
    manifest = _load_manifest(manifest_path) if not rebuild_manifest \
                else _load_manifest("/nonexistent")
    completed = set(manifest.get("completed_segments", {}).keys())
    pending = [t for t in targets if _segment_uid(t) not in completed]
    if progress_to_stderr:
        print(f"[phase3] {len(completed):,} already extracted, "
              f"{len(pending):,} pending",
              file=sys.stderr, flush=True)

    if not pending:
        return {"status": "nothing-to-do",
                "already_done": len(completed)}

    # Step 3: extract via Sonnet, write vault notes.
    client = AnthropicClient(model=EXTRACTION_MODEL)
    aggregate = {
        "targets_attempted":   0,
        "targets_extracted":   0,
        "targets_written":     0,
        "targets_errored":     0,
        "targets_skipped_guard": 0,
        "input_tokens":        0,
        "output_tokens":       0,
        "cost_usd":            0.0,
        "by_kind":             {},
    }
    counter = {"done": 0}
    written_paths: list[str] = []
    last_save = time.monotonic()

    def _process(t: ExtractionTarget) -> dict:
        out = {"target": t, "extracted": None, "path": "",
               "in_tok": 0, "out_tok": 0, "cost": 0.0, "error": "",
               "skipped": ""}
        guard = fiction_guard_reason(t.content)
        if guard:
            out["skipped"] = guard
            print(f"[phase3] SKIP (own-fiction guard): {_segment_uid(t)} — "
                  f"{guard}", file=sys.stderr, flush=True)
            return out
        parsed, ti, to, cost, err = extract_segment(t, client=client)
        out["in_tok"], out["out_tok"], out["cost"] = ti, to, cost
        if err:
            out["error"] = err
            return out
        out["extracted"] = parsed
        self_report = extraction_self_reports_failure(parsed)
        if self_report:
            out["skipped"] = self_report
            print(f"[phase3] SKIP (no article found): {_segment_uid(t)} — "
                  f"{self_report}", file=sys.stderr, flush=True)
            return out
        try:
            out["path"] = write_vault_note(t, parsed,
                                           resources_root=resources_root)
        except Exception as e:
            out["error"] = f"write: {e}"
        return out

    def _record(r: dict) -> None:
        t = r["target"]
        aggregate["targets_attempted"] += 1
        aggregate["input_tokens"]      += r["in_tok"]
        aggregate["output_tokens"]     += r["out_tok"]
        aggregate["cost_usd"]          += r["cost"]
        kind_stat = aggregate["by_kind"].setdefault(t.seg_kind,
                        {"attempted": 0, "written": 0, "errored": 0,
                         "skipped_guard": 0})
        kind_stat["attempted"] += 1
        if r["skipped"]:
            aggregate["targets_skipped_guard"] += 1
            kind_stat["skipped_guard"] = kind_stat.get("skipped_guard", 0) + 1
        elif r["error"]:
            aggregate["targets_errored"] += 1
            kind_stat["errored"] += 1
        elif r["extracted"]:
            aggregate["targets_extracted"] += 1
            if r["path"]:
                aggregate["targets_written"] += 1
                kind_stat["written"] += 1
                written_paths.append(r["path"])
        manifest["completed_segments"][_segment_uid(t)] = {
            "kind":         t.seg_kind,
            "path":         r["path"],
            "input_tokens": r["in_tok"],
            "output_tokens": r["out_tok"],
            "cost_usd":     r["cost"],
            "error":        r["error"],
            "skipped":      r["skipped"],
        }
        m_totals = manifest["totals"]
        m_totals["segments_extracted"] += (1 if r["extracted"] else 0)
        m_totals["segments_written"]   += (1 if r["path"] else 0)
        m_totals["input_tokens"]       += r["in_tok"]
        m_totals["output_tokens"]      += r["out_tok"]
        m_totals["cost_usd"]           += r["cost"]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, t): t for t in pending}
        for fut in as_completed(futures):
            r = fut.result()
            counter["done"] += 1
            _record(r)
            now = time.monotonic()
            if counter["done"] % 25 == 0 or (now - last_save) > 30:
                _save_manifest(manifest, manifest_path)
                last_save = now
            if progress_to_stderr and counter["done"] % 50 == 0:
                pct = counter["done"] / len(pending) * 100
                rate = counter["done"] / max(0.1, now - start)
                eta_min = (len(pending) - counter["done"]) / max(0.001, rate) / 60
                print(f"[phase3] {counter['done']:,}/{len(pending):,} "
                      f"({pct:.1f}%, {now-start:.0f}s, ETA {eta_min:.0f}m) "
                      f"written={aggregate['targets_written']:,} "
                      f"errored={aggregate['targets_errored']:,} "
                      f"cost=${aggregate['cost_usd']:.2f}",
                      file=sys.stderr, flush=True)

    _save_manifest(manifest, manifest_path)

    # Step 4: index the new notes into the knowledge collection so they
    # are retrievable without a manual CLI run. Fail-open (logged) —
    # never blocks the pipeline.
    if index_to_knowledge:
        aggregate["knowledge_index"] = index_notes_into_knowledge(
            written_paths, progress_to_stderr=progress_to_stderr,
        )
    else:
        aggregate["knowledge_index"] = {"skipped": True}

    aggregate["duration_secs"] = time.monotonic() - start
    return aggregate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3 — extract news/opinion/resource segments to vault notes.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--resources-root", default=DEFAULT_RESOURCES_ROOT,
                        help="Flat vault Resources/ folder notes land in")
    parser.add_argument("--chain-index", default=CHAIN_INDEX_DEFAULT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip ChromaDB knowledge indexing of new notes")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    stats = run_phase3(
        archive_dir=args.archive_dir,
        resources_root=args.resources_root,
        chain_index_path=args.chain_index,
        manifest_path=args.manifest,
        max_workers=args.max_workers,
        progress_to_stderr=not args.quiet,
        rebuild_manifest=args.rebuild_manifest,
        limit=args.limit,
        index_to_knowledge=not args.no_index,
    )
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_RESOURCES_ROOT",
    "DEFAULT_MANIFEST_PATH",
    "EXTRACTION_MODEL",
    "ExtractionTarget",
    "find_extraction_targets",
    "extract_segment",
    "fiction_guard_reason",
    "extraction_self_reports_failure",
    "build_vault_note",
    "write_vault_note",
    "index_notes_into_knowledge",
    "run_phase3",
    "main",
]
