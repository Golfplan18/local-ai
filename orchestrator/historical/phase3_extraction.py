"""Phase 3 — extract news, opinion, and resource pasted segments
from the cleaned-pair archive into structured vault notes.

For each pasted segment in `~/Documents/Commercial AI archives/`
classified as `news`, `opinion`, or `resource`:

  - Send the segment content to Sonnet with a type-specific extraction
    prompt that returns JSON (headline, lede, key facts, quotes, etc.)
  - Template the JSON into a Schema §12-compatible vault note
  - For opinion: also capture the user's reaction (the personal-voice
    portions of the same pair's `cleaned_user_input`)
  - Write to `~/Documents/vault/Sources/{News,Opinion,Resources}/[YYYY]/`

A manifest at `~/ora/data/phase3-manifest.json` tracks per-segment
completion so re-runs skip already-extracted segments. Segment id is
`<file_basename>_seg<N>` where N is the segment's index within the
pair.

Output filename: `YYYY-MM-DD_<slug>.md` (slug derived from headline /
title, sanitized to lowercase ASCII + hyphens). Collisions append
`-seg<N>` to disambiguate.
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
DEFAULT_SOURCES_ROOT   = "/Users/oracle/Documents/vault/Sources"
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

# Folders by type
_FOLDER_BY_TYPE = {
    "news":     "News",
    "opinion":  "Opinion",
    "resource": "Resources",
}


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
                     sources_root: str) -> Path:
    """Compute the vault output path for an extracted segment."""
    when = target.when or datetime.now()
    year = str(when.year)
    folder = _FOLDER_BY_TYPE[target.seg_kind]
    if target.seg_kind == "news":
        slug_src = extracted.get("headline") or ""
    elif target.seg_kind == "opinion":
        slug_src = extracted.get("headline") or ""
    else:
        slug_src = extracted.get("title") or ""
    slug = _slugify(slug_src) or "untitled"
    base = f"{when.strftime('%Y-%m-%d')}_{slug}.md"
    return Path(sources_root) / folder / year / base


def write_vault_note(
    target:        ExtractionTarget,
    extracted:     dict,
    sources_root:  str = DEFAULT_SOURCES_ROOT,
) -> str:
    """Write the vault note. Returns the absolute path written."""
    path = _vault_path_for(target, extracted, sources_root)
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
    sources_root:       str = DEFAULT_SOURCES_ROOT,
    chain_index_path:   str = CHAIN_INDEX_DEFAULT,
    manifest_path:      str = DEFAULT_MANIFEST_PATH,
    max_workers:        int = 6,
    progress_to_stderr: bool = True,
    rebuild_manifest:   bool = False,
    limit:              Optional[int] = None,
) -> dict:
    """Walk the archive, extract every news/opinion/resource segment,
    write vault notes."""
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
        "input_tokens":        0,
        "output_tokens":       0,
        "cost_usd":            0.0,
        "by_kind":             {},
    }
    counter = {"done": 0}
    last_save = time.monotonic()

    def _process(t: ExtractionTarget) -> dict:
        out = {"target": t, "extracted": None, "path": "",
               "in_tok": 0, "out_tok": 0, "cost": 0.0, "error": ""}
        parsed, ti, to, cost, err = extract_segment(t, client=client)
        out["in_tok"], out["out_tok"], out["cost"] = ti, to, cost
        if err:
            out["error"] = err
            return out
        out["extracted"] = parsed
        try:
            out["path"] = write_vault_note(t, parsed, sources_root=sources_root)
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
                        {"attempted": 0, "written": 0, "errored": 0})
        kind_stat["attempted"] += 1
        if r["error"]:
            aggregate["targets_errored"] += 1
            kind_stat["errored"] += 1
        elif r["extracted"]:
            aggregate["targets_extracted"] += 1
            if r["path"]:
                aggregate["targets_written"] += 1
                kind_stat["written"] += 1
        manifest["completed_segments"][_segment_uid(t)] = {
            "kind":         t.seg_kind,
            "path":         r["path"],
            "input_tokens": r["in_tok"],
            "output_tokens": r["out_tok"],
            "cost_usd":     r["cost"],
            "error":        r["error"],
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
    parser.add_argument("--sources-root", default=DEFAULT_SOURCES_ROOT)
    parser.add_argument("--chain-index", default=CHAIN_INDEX_DEFAULT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    stats = run_phase3(
        archive_dir=args.archive_dir,
        sources_root=args.sources_root,
        chain_index_path=args.chain_index,
        manifest_path=args.manifest,
        max_workers=args.max_workers,
        progress_to_stderr=not args.quiet,
        rebuild_manifest=args.rebuild_manifest,
        limit=args.limit,
    )
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_SOURCES_ROOT",
    "DEFAULT_MANIFEST_PATH",
    "EXTRACTION_MODEL",
    "ExtractionTarget",
    "find_extraction_targets",
    "extract_segment",
    "build_vault_note",
    "write_vault_note",
    "run_phase3",
    "main",
]
