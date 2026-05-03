"""Vault entry writer for transcripts — Audio/Video Phase 2.

Writes a single markdown note to the vault root (no folders — the vault
is properties-organized, not folder-organized) per the user's standing
directive. The note carries::

    type: transcript                   # added to YAML schema §4 in this phase
    tags: [incubating]                 # standard "needs triage" status
    source_media: <abs path>
    transcribed_at: <ISO 8601>
    transcription_model: <model name>
    language: <detected ISO code>
    duration_ms: <number>
    segment_count: <number>

Body has two sections:

  ## Transcript
  <plain prose, paragraph-wrapped>

  ## Segments
  - **00:00:00 → 00:00:05** segment text
  - ...

The Segments section preserves Whisper utterance timestamps so future
features (transcript-to-timeline jump in Phase 8) can hop into the
recording without re-transcribing.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path(os.path.expanduser("~/Documents/vault")).resolve()


# ── helpers ──────────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    """Vault-friendly slug — keep words and dashes, drop the rest."""
    s = re.sub(r"[^\w\s\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _format_ms_as_hms(ms: float | int | None) -> str:
    if ms is None:
        return "00:00:00"
    total = max(0, int(ms))
    h, rem = divmod(total // 1000, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _wrap_paragraphs(text: str, max_chars: int = 110) -> str:
    """Cheap paragraph wrap. Whisper output is one stream; we add a paragraph
    break at sentence boundaries every ~3 sentences for readability."""
    text = (text or "").strip()
    if not text:
        return ""
    # Split on sentence-ish boundaries.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    paragraphs: list[str] = []
    cur: list[str] = []
    cur_len = 0
    sentences_in_para = 0
    for sent in sentences:
        cur.append(sent)
        cur_len += len(sent) + 1
        sentences_in_para += 1
        if sentences_in_para >= 3 or cur_len >= max_chars * 3:
            paragraphs.append(" ".join(cur))
            cur = []
            cur_len = 0
            sentences_in_para = 0
    if cur:
        paragraphs.append(" ".join(cur))
    return "\n\n".join(paragraphs)


def _build_filename(source_path: Path, transcribed_at: datetime) -> str:
    """Return a vault filename like ``Transcript — <source-stem> — YYYY-MM-DD.md``.

    The em-dash matches existing vault filename conventions (``Reference —``,
    ``Working — Framework —``, etc.).
    """
    stem = _slugify(source_path.stem)
    if not stem:
        stem = "recording"
    # Clip super-long source names so the vault filename stays manageable.
    if len(stem) > 60:
        stem = stem[:60].rstrip(" -_")
    date_part = transcribed_at.strftime("%Y-%m-%d")
    return f"Transcript — {stem} — {date_part}.md"


def _ensure_unique(path: Path) -> Path:
    """If ``path`` exists, append ``- 2``, ``- 3``, … until a free slot is found."""
    if not path.exists():
        return path
    base = path.with_suffix("")
    suffix = path.suffix or ".md"
    counter = 2
    while True:
        candidate = Path(f"{base} - {counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


# ── public surface ───────────────────────────────────────────────────────────

def write_transcript_note(
    *,
    source_media_path: str | Path,
    plain_text: str,
    segments: list[dict],
    language: str | None,
    duration_ms: float | None,
    transcription_model: str = "whisper-large-v3-local",
    extra_tags: list[str] | None = None,
    vault_root: str | Path | None = None,
) -> Path:
    """Render a transcript to a single vault markdown note and write it.

    Returns the vault path of the new note. The caller (server endpoint)
    propagates this so the client UI can present it in the input pane
    or follow-up flows.
    """
    source = Path(source_media_path)
    root = Path(vault_root) if vault_root else VAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)

    transcribed_at = datetime.now(timezone.utc)

    filename = _build_filename(source, transcribed_at)
    target = _ensure_unique(root / filename)

    # YAML — keep keys alphabetized within sections so future diffs are
    # readable. Quoting policy: paths and ISO timestamps use double quotes
    # because they may contain colons or other YAML-special characters.
    tags: list[str] = ["incubating"]
    if extra_tags:
        for t in extra_tags:
            t_clean = (t or "").strip()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)

    yaml_lines = [
        "---",
        "type: transcript",
        "tags:",
    ]
    for tag in tags:
        yaml_lines.append(f"  - {tag}")
    yaml_lines += [
        f'source_media: "{source}"',
        f'transcribed_at: "{transcribed_at.isoformat(timespec="seconds")}"',
        f"transcription_model: {transcription_model}",
    ]
    if language:
        yaml_lines.append(f"language: {language}")
    if duration_ms is not None:
        yaml_lines.append(f"duration_ms: {int(duration_ms)}")
    yaml_lines.append(f"segment_count: {len(segments)}")
    yaml_lines.append("---")

    # Body
    body_lines: list[str] = []
    body_lines.append("")
    title_stem = _slugify(source.stem) or "recording"
    body_lines.append(f"# Transcript — {title_stem}")
    body_lines.append("")
    body_lines.append(
        f"Auto-generated transcript of `{source.name}`. "
        f"Tagged `incubating` — review for atomic-note extraction or elevate as-is."
    )
    body_lines.append("")
    body_lines.append("## Transcript")
    body_lines.append("")
    body_lines.append(_wrap_paragraphs(plain_text))
    body_lines.append("")
    if segments:
        body_lines.append("## Segments")
        body_lines.append("")
        for seg in segments:
            start_hms = _format_ms_as_hms(seg.get("start_ms"))
            end_hms = _format_ms_as_hms(seg.get("end_ms"))
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            body_lines.append(f"- **{start_hms} → {end_hms}** {text}")
        body_lines.append("")

    note_text = "\n".join(yaml_lines) + "\n" + "\n".join(body_lines)
    target.write_text(note_text, encoding="utf-8")
    return target


__all__ = ["write_transcript_note", "VAULT_ROOT"]
