"""LLM-based reclassification of `other`-tagged pasted segments.

The heuristic classifier is conservative — most pasted segments end up
in the catch-all `other` bucket because the discriminative signals
(headline + webpage chrome) aren't always present in pastes. This
module sends those `other` segments to Haiku 4.5 for a one-shot
classification call, then updates the cleaned-pair file's annotation
block with the new label.

Scope: only `other`-tagged segments with content length ≥ 500 chars
(shorter segments are usually dialogue fragments or snippets — not
worth a classification call). Other classifications (news / opinion /
resource / earlier-draft) are left untouched.

Cost: ~$30 for the full archive at typical segment sizes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from orchestrator.historical.api_client import AnthropicClient
from orchestrator.historical.cleaned_pair_reader import (
    CleanedPairFile,
    load_cleaned_pair,
)
from orchestrator.historical.paste_detection import (
    Segment,
    process_user_input,
)
from orchestrator.historical.reclassify_pastes import (
    _format_pasted_segments_block,
    _rewrite_pasted_segments_in_file,
)
from orchestrator.tools.vault_indexer import (
    INDEX_DEFAULT,
    load_index,
)


DEFAULT_ARCHIVE_DIR  = "/Users/oracle/Documents/Commercial AI archives"
DEFAULT_MANIFEST_PATH = "/Users/oracle/ora/data/llm-reclassify-manifest.json"
DEFAULT_REPORT_PATH   = "/Users/oracle/ora/data/llm-reclassify-report.json"

# Min segment length to bother classifying. Shorter segments are usually
# dialogue fragments or one-line snippets — not worth a model call.
MIN_SEGMENT_CHARS_FOR_LLM = 500
# Cap segment text sent to the model — Haiku has plenty of context but
# we don't need 100K of an article to classify; first ~3K chars is fine.
MAX_SEGMENT_CHARS_FOR_LLM = 3_000

# Valid LLM responses. Anything else falls back to "other".
_VALID_LABELS = frozenset({
    "news", "opinion", "resource", "user-content", "other",
})


# ---------------------------------------------------------------------------
# LLM classification prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You classify pasted text snippets from someone's AI \
chat history. Each snippet was pasted into a chat conversation and \
needs to be tagged so downstream tooling knows whether it's the user's \
own writing or third-party content.

Categories — pick exactly ONE and reply with ONLY a single word:

- news: a news article (third-person reportage of current events; \
typically political, business, technology, or general news; often \
includes journalist attribution like "officials said" or "sources \
confirmed"; no first-person opinion stance)

- opinion: a signed opinion piece — op-ed, columnist, blog post, or \
substack-style essay (first-person argument with a clear personal \
stance; "I think", "the case for", "why X is wrong", written as one \
person's view)

- resource: a research paper, technical document, formal reference \
material with citations, methodology sections, or structured headings \
typical of academic/technical writing

- user-content: the user's own writing — character outlines, framework \
documents, narrative drafts, story beats, notes, instructions to \
themselves, project planning documents, content templates. Often has \
distinctive vocabulary (project names, character names, framework \
names). Even when long and structured, this is the user's voice or \
work product.

- other: doesn't fit any of the above — code blocks, raw data, \
dialogue snippets, JSON/YAML, terminal output, fragments, or anything \
ambiguous

Reply with ONE word: news, opinion, resource, user-content, or other. \
No explanation, no punctuation."""


def _classify_one_segment(
    client: AnthropicClient,
    content: str,
    *,
    max_tokens: int = 8,
) -> tuple[str, int, int, float]:
    """Classify a single segment via Haiku. Returns (label, in_tok,
    out_tok, cost). Falls back to 'other' on any model error."""
    truncated = content[:MAX_SEGMENT_CHARS_FOR_LLM]
    user_msg = f"<<<SNIPPET\n{truncated}\nSNIPPET>>>\n\nClassification:"
    result = client.call(
        system=_SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    if result.error:
        return "other", result.input_tokens, result.output_tokens, result.cost_usd
    label = result.text.strip().lower()
    # Strip punctuation / whitespace.
    label = re.sub(r"[^a-z\-]", "", label)
    if label not in _VALID_LABELS:
        # Sometimes the model returns "user_content" with underscore
        # instead of hyphen; normalize.
        if label == "usercontent" or label == "user_content":
            label = "user-content"
        else:
            label = "other"
    return label, result.input_tokens, result.output_tokens, result.cost_usd


# ---------------------------------------------------------------------------
# Per-file orchestration
# ---------------------------------------------------------------------------


@dataclass
class FileResult:
    file_path:           str
    segments_classified: int = 0
    segments_changed:    int = 0
    transitions:         dict = field(default_factory=dict)
    file_written:        bool = False
    error:               str = ""
    input_tokens:        int = 0
    output_tokens:       int = 0
    cost_usd:            float = 0.0


def _llm_label_to_classification(label: str) -> str:
    """Map LLM label → cleaned-pair classification. The four-bucket
    schema uses {news, opinion, resource, earlier-draft, other}; the
    LLM's `user-content` label maps to `other` because the cleanup
    pipeline doesn't distinguish user's-own-paste from generic other.
    Vault-matched earlier-drafts aren't reclassified here (we never
    touch non-`other` segments)."""
    return {
        "news":         "news",
        "opinion":      "opinion",
        "resource":     "resource",
        "user-content": "other",
        "other":        "other",
    }.get(label, "other")


def reclassify_one_file(
    file_path: str,
    *,
    client: AnthropicClient,
    vault_index: Optional[dict],
    min_seg_chars: int = MIN_SEGMENT_CHARS_FOR_LLM,
) -> FileResult:
    """Reclassify the `other`-tagged segments (≥ min_seg_chars) in one
    cleaned-pair file via LLM. Writes the file back if any classification
    changed."""
    res = FileResult(file_path=file_path)
    try:
        cp = load_cleaned_pair(file_path)
    except Exception as e:
        res.error = f"load: {e}"
        return res

    # Re-run paste detection so we have access to per-segment content.
    segments = process_user_input(
        cp.cleaned_user_input,
        vault_index=vault_index,
        source_platform=cp.source_platform,
    )

    # Find candidates: pasted, classified "other", and long enough.
    transitions: Counter = Counter()
    changes_made = 0
    classified = 0

    for seg in segments:
        if seg.kind != "pasted":
            continue
        if seg.classification != "other":
            continue
        if len(seg.content) < min_seg_chars:
            continue
        try:
            label, ti, to, cost = _classify_one_segment(client, seg.content)
        except Exception as e:
            res.error = f"llm: {e}"
            continue
        classified += 1
        res.input_tokens  += ti
        res.output_tokens += to
        res.cost_usd      += cost
        new_class = _llm_label_to_classification(label)
        if new_class != seg.classification:
            transitions[(seg.classification, new_class)] += 1
            changes_made += 1
            seg.classification = new_class
            seg.heuristic_flags = sorted(set(
                list(seg.heuristic_flags) + [f"llm-reclassified:{label}"]
            ))

    res.segments_classified = classified
    res.segments_changed    = changes_made
    res.transitions         = {f"{a}→{b}": n for (a, b), n in transitions.items()}

    if changes_made > 0:
        # Rebuild the Pasted segments annotation block from the updated
        # segments. Only PASTED segments go in the annotation.
        pasted = [s for s in segments if s.kind == "pasted"]
        new_block = _format_pasted_segments_block(pasted)
        try:
            res.file_written = _rewrite_pasted_segments_in_file(
                file_path, new_block,
            )
        except Exception as e:
            res.error = f"write: {e}"
    return res


# ---------------------------------------------------------------------------
# Manifest (resume-aware)
# ---------------------------------------------------------------------------


def _load_manifest(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {
            "version":          1,
            "created_at":       datetime.now().isoformat(timespec="seconds"),
            "completed_files":  {},
            "totals": {
                "files_done":          0,
                "segments_classified": 0,
                "segments_changed":    0,
                "input_tokens":        0,
                "output_tokens":       0,
                "cost_usd":            0.0,
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
# Batch
# ---------------------------------------------------------------------------


def reclassify_archive_with_llm(
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
    *,
    vault_index_path:   str = INDEX_DEFAULT,
    manifest_path:      str = DEFAULT_MANIFEST_PATH,
    max_workers:        int = 8,
    progress_to_stderr: bool = True,
    limit:              Optional[int] = None,
    rebuild_manifest:   bool = False,
) -> dict:
    """Walk the archive, send `other`-tagged ≥500-char pasted segments
    to Haiku for reclassification, write changed annotations back."""
    start = time.monotonic()

    try:
        vault_index = load_index(vault_index_path)
    except Exception as e:
        if progress_to_stderr:
            print(f"[llm-reclass] vault index unavailable ({e}); proceeding "
                  f"without earlier-draft override", file=sys.stderr)
        vault_index = {"entries": []}

    client = AnthropicClient()

    manifest = _load_manifest(manifest_path) if not rebuild_manifest else _load_manifest("/nonexistent")
    completed_set = set(manifest.get("completed_files", {}).keys())

    files = sorted(Path(archive_dir).glob("*.md"))
    if limit:
        files = files[:limit]
    targets = [str(f) for f in files if str(f) not in completed_set]
    if progress_to_stderr:
        print(f"[llm-reclass] {len(files):,} files in archive, "
              f"{len(completed_set):,} already done, "
              f"{len(targets):,} to process (max_workers={max_workers})",
              file=sys.stderr, flush=True)

    if not targets:
        return {"status": "nothing-to-do",
                "files_already_done": len(completed_set)}

    aggregate = {
        "files_attempted":  0,
        "files_changed":    0,
        "files_unchanged":  0,
        "files_errored":    0,
        "segments_classified": 0,
        "segments_changed": 0,
        "transitions":      Counter(),
        "input_tokens":     0,
        "output_tokens":    0,
        "cost_usd":         0.0,
    }
    counter = {"done": 0}
    last_save = time.monotonic()

    def _process(path: str) -> FileResult:
        return reclassify_one_file(
            path, client=client, vault_index=vault_index,
        )

    def _record(r: FileResult) -> None:
        aggregate["files_attempted"]      += 1
        aggregate["segments_classified"]  += r.segments_classified
        aggregate["segments_changed"]     += r.segments_changed
        aggregate["input_tokens"]         += r.input_tokens
        aggregate["output_tokens"]        += r.output_tokens
        aggregate["cost_usd"]             += r.cost_usd
        for k, v in r.transitions.items():
            aggregate["transitions"][k] += v
        if r.error:
            aggregate["files_errored"] += 1
        elif r.file_written:
            aggregate["files_changed"] += 1
        else:
            aggregate["files_unchanged"] += 1
        manifest["completed_files"][r.file_path] = {
            "segments_classified": r.segments_classified,
            "segments_changed":    r.segments_changed,
            "input_tokens":        r.input_tokens,
            "output_tokens":       r.output_tokens,
            "cost_usd":            r.cost_usd,
            "error":               r.error,
        }
        manifest["totals"]["files_done"]          = len(manifest["completed_files"])
        manifest["totals"]["segments_classified"] += r.segments_classified
        manifest["totals"]["segments_changed"]    += r.segments_changed
        manifest["totals"]["input_tokens"]        += r.input_tokens
        manifest["totals"]["output_tokens"]       += r.output_tokens
        manifest["totals"]["cost_usd"]            += r.cost_usd

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, p): p for p in targets}
        for fut in as_completed(futures):
            r = fut.result()
            counter["done"] += 1
            _record(r)
            now = time.monotonic()
            # Persist manifest every 50 files OR every 30 seconds.
            if counter["done"] % 50 == 0 or (now - last_save) > 30:
                _save_manifest(manifest, manifest_path)
                last_save = now
            if progress_to_stderr and counter["done"] % 100 == 0:
                pct = counter["done"] / len(targets) * 100
                rate = counter["done"] / max(0.1, now - start)
                eta_min = (len(targets) - counter["done"]) / max(0.001, rate) / 60
                print(f"[llm-reclass] {counter['done']:,}/{len(targets):,} "
                      f"({pct:.1f}%, {now-start:.0f}s, ETA {eta_min:.0f}m) "
                      f"changed={aggregate['files_changed']:,} "
                      f"segments={aggregate['segments_classified']:,} "
                      f"cost=${aggregate['cost_usd']:.2f}",
                      file=sys.stderr, flush=True)

    _save_manifest(manifest, manifest_path)
    aggregate["transitions"] = dict(aggregate["transitions"])
    aggregate["duration_secs"] = time.monotonic() - start
    return aggregate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="LLM-based reclassification of `other` pasted segments.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rebuild-manifest", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    stats = reclassify_archive_with_llm(
        archive_dir=args.archive_dir,
        manifest_path=args.manifest,
        max_workers=args.max_workers,
        progress_to_stderr=not args.quiet,
        limit=args.limit,
        rebuild_manifest=args.rebuild_manifest,
    )
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_MANIFEST_PATH",
    "MIN_SEGMENT_CHARS_FOR_LLM",
    "FileResult",
    "reclassify_one_file",
    "reclassify_archive_with_llm",
    "main",
]
